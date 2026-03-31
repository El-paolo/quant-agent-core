"""
Hidden Markov Model for market regime detection.

Fits a Gaussian HMM to log-returns to identify latent market regimes
(e.g. low-volatility, high-volatility, crisis). The model is used for
contextual analysis, not trading signals.

Uses a train/test split (default 80/20) to provide out-of-sample
log-likelihood as a validation metric.

Minimum ~100 observations recommended for meaningful regime detection.
"""

import warnings

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError

_MIN_OBS = 100
_DEFAULT_N_STATES = 3
_DEFAULT_TRAIN_RATIO = 0.80
_REGIME_LABELS = {
    "low_vol": "Baja volatilidad",
    "mid_vol": "Volatilidad moderada",
    "high_vol": "Alta volatilidad",
}


def fit_hmm(
    returns: pd.Series,
    n_states: int = _DEFAULT_N_STATES,
    train_ratio: float = _DEFAULT_TRAIN_RATIO,
) -> dict:
    """
    Fit a Gaussian HMM to returns and identify market regimes.

    States are ordered by variance (ascending): the lowest-variance state
    is labeled 'low_vol', the highest 'high_vol'.

    The data is split into train/test sets. The model is fit on the train
    set only; the test set provides an out-of-sample log-likelihood score
    for validation.

    Args:
        returns:      Log-returns series (daily).
        n_states:     Number of hidden states (2 or 3).
        train_ratio:  Fraction of data used for training (0.5–0.95).

    Returns:
        dict with keys:
          - states: pd.Series of regime labels aligned with returns index
          - state_sequence: pd.Series of integer state IDs
          - current_regime: dict with label, since_date, duration_days
          - state_params: list of dicts with {label, mean, std, stationary_prob}
          - distributions: list of dicts with {label, label_es, mean, std, x, pdf}
          - transition_matrix: nested list (n_states x n_states)
          - split: dict with train_size, test_size, train_ratio
          - train_score: float (per-sample log-likelihood on train set)
          - test_score: float (per-sample log-likelihood on test set)
          - n_states: int
          - observations: int
          - log_likelihood: float
          - aic: float
          - bic: float

    Raises:
        MetricsError: If data is insufficient or model fails to converge.
    """
    from hmmlearn.hmm import GaussianHMM

    clean = returns.dropna()
    if len(clean) < _MIN_OBS:
        raise MetricsError(
            f"HMM requires at least {_MIN_OBS} observations, got {len(clean)}"
        )

    if n_states not in (2, 3):
        raise MetricsError("HMM supports 2 or 3 states")

    if not 0.5 <= train_ratio <= 0.95:
        raise MetricsError("train_ratio must be between 0.5 and 0.95")

    # ── Train/test split (temporal, no shuffle) ──
    split_idx = int(len(clean) * train_ratio)
    train = clean.iloc[:split_idx]
    test = clean.iloc[split_idx:]

    X_train = train.values.reshape(-1, 1)
    X_test = test.values.reshape(-1, 1)
    X_full = clean.values.reshape(-1, 1)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="full",
                n_iter=200,
                random_state=42,
                tol=1e-4,
            )
            model.fit(X_train)
    except Exception as exc:
        raise MetricsError(f"HMM fitting failed: {exc}") from exc

    # ── Scores ──
    train_score = float(model.score(X_train) / len(X_train))  # per-sample
    test_score = float(model.score(X_test) / len(X_test))

    # Decode most likely state sequence on FULL data
    state_seq = model.predict(X_full)

    # ── Order states by variance (ascending) ──
    state_vars = []
    for i in range(n_states):
        cov = model.covars_[i]
        var = float(cov.flatten()[0]) if hasattr(cov, "flatten") else float(cov)
        state_vars.append(var)

    order = np.argsort(state_vars)  # lowest variance first
    label_keys = ["low_vol", "mid_vol", "high_vol"][:n_states]

    # Map: original_state_id → ordered_rank
    rank_map = {int(orig): rank for rank, orig in enumerate(order)}
    ordered_seq = np.array([rank_map[s] for s in state_seq])

    # Build label series
    label_list = [label_keys[rank_map[s]] for s in state_seq]
    states = pd.Series(label_list, index=clean.index, name="regime")
    state_ids = pd.Series(ordered_seq, index=clean.index, name="state")

    # ── Transition matrix & stationary distribution ──
    transmat = model.transmat_
    try:
        reordered_trans = transmat[np.ix_(order, order)]
        eigvals, eigvecs = np.linalg.eig(reordered_trans.T)
        stat_idx = np.argmin(np.abs(eigvals - 1.0))
        stationary = np.real(eigvecs[:, stat_idx])
        stationary = stationary / stationary.sum()
    except Exception:
        stationary = np.ones(n_states) / n_states
        reordered_trans = transmat

    # ── State parameters ──
    state_params = []
    for rank, orig_id in enumerate(order):
        mean_val = float(model.means_[orig_id][0])
        std_val = float(np.sqrt(state_vars[orig_id]))
        state_params.append({
            "label": label_keys[rank],
            "label_es": _REGIME_LABELS.get(label_keys[rank], label_keys[rank]),
            "mean_return": mean_val,
            "std": std_val,
            "annualized_vol": std_val * np.sqrt(252),
            "stationary_prob": float(stationary[rank]),
        })

    # ── Distributions (Gaussian PDFs for charting) ──
    all_returns = clean.values
    x_min = float(np.min(all_returns)) * 1.3
    x_max = float(np.max(all_returns)) * 1.3
    x_range = np.linspace(x_min, x_max, 200)

    distributions = []
    for sp in state_params:
        mu = sp["mean_return"]
        sigma = sp["std"]
        pdf = (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(
            -0.5 * ((x_range - mu) / sigma) ** 2
        )
        distributions.append({
            "label": sp["label"],
            "label_es": sp["label_es"],
            "mean": mu,
            "std": sigma,
            "x": [round(float(v), 6) for v in x_range],
            "pdf": [round(float(v), 4) for v in pdf],
        })

    # ── Current regime info ──
    current_label = label_list[-1]
    current_state = state_seq[-1]
    streak = 1
    for i in range(len(state_seq) - 2, -1, -1):
        if state_seq[i] == current_state:
            streak += 1
        else:
            break

    since_idx = len(clean) - streak
    since_date = str(
        clean.index[since_idx].date()
        if hasattr(clean.index[since_idx], "date")
        else clean.index[since_idx]
    )

    # ── AIC / BIC (on train set) ──
    n_params = n_states * n_states + 2 * n_states - 1
    log_like = float(model.score(X_train) * len(X_train))
    aic = -2 * log_like + 2 * n_params
    bic = -2 * log_like + n_params * np.log(len(X_train))

    return {
        "states": states,
        "state_sequence": state_ids,
        "current_regime": {
            "label": current_label,
            "label_es": _REGIME_LABELS.get(current_label, current_label),
            "since_date": since_date,
            "duration_days": streak,
        },
        "state_params": state_params,
        "distributions": distributions,
        "transition_matrix": reordered_trans.tolist(),
        "split": {
            "train_size": len(train),
            "test_size": len(test),
            "train_ratio": train_ratio,
        },
        "train_score": train_score,
        "test_score": test_score,
        "n_states": n_states,
        "observations": len(clean),
        "log_likelihood": log_like,
        "aic": float(aic),
        "bic": float(bic),
    }
