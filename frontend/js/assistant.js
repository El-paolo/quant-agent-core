/* ============================================================
   FINA — Q&A Assistant (Drawer)
   ============================================================ */

(() => {
  "use strict";

  const F = window.FINA;
  const state = F.state;
  const $ = F.$;

  /* ─── Toggle drawer ─── */
  const openDrawer = () => {
    state.chatOpen = true;
    $.assistantDrawer.classList.remove("hidden");
    $.assistantFab.classList.add("hidden");
    $.assistantInput.focus();
  };

  const closeDrawer = () => {
    state.chatOpen = false;
    $.assistantDrawer.classList.add("hidden");
    $.assistantFab.classList.remove("hidden");
  };

  $.assistantFab.addEventListener("click", openDrawer);
  $.assistantClose.addEventListener("click", closeDrawer);

  /* ─── Gather context from current state ─── */
  const gatherContext = () => {
    const ctx = {};

    if (state.ticker) ctx.ticker = state.ticker;
    if (state.period) ctx.period = state.period;

    if (state.analysisResult && state.analysisResult.data) {
      const c = state.analysisResult.data.computed || {};
      if (c.sharpe) ctx.sharpe = F.fmt(c.sharpe.sharpe_ratio);
      if (c.sortino) ctx.sortino = F.fmt(c.sortino.sortino_ratio);
      if (c.beta) ctx.beta = F.fmt(c.beta.beta);
      if (c.rsi) ctx.rsi = F.fmt(c.rsi.latest, 1);
      if (c.rolling_volatility) ctx.volatility = F.fmtPct(c.rolling_volatility.latest_sd);
      if (c.returns) ctx.annualized_return = F.fmtSign(c.returns.mean * 252);
    }

    if (state.modelsResult) {
      const m = state.modelsResult;
      if (m.garch && m.garch.diagnostics) {
        ctx.garch_persistence = F.fmt(m.garch.diagnostics.persistence, 4);
      }
      if (m.hmm && m.hmm.current_regime) {
        ctx.hmm_regime = m.hmm.current_regime.label_es;
      }
      if (m.arima && m.arima.diagnostics) {
        ctx.arima_order = m.arima.diagnostics.order;
      }
    }

    if (state.comparisonResult && state.comparisonResult.verdict) {
      ctx.comparison_verdict = state.comparisonResult.verdict.summary_es;
    }

    if (state.backtestResult && state.backtestResult.metrics) {
      const s = state.backtestResult.metrics.strategy;
      if (s) {
        ctx.backtest_sharpe = F.fmt(s.sharpe_ratio, 2);
        ctx.backtest_return = F.fmtSign(s.total_return);
        ctx.backtest_max_drawdown = F.fmtPct(s.max_drawdown);
      }
    }

    if (state.monteCarloResult && state.monteCarloResult.metrics_distribution) {
      const md = state.monteCarloResult.metrics_distribution;
      ctx.mc_prob_profit = F.fmtPct(md.prob_profit);
      ctx.mc_var_95 = F.fmtPct(md.var_95);
      ctx.mc_prob_beat_bh = F.fmtPct(md.prob_beat_benchmark);
    }

    return Object.keys(ctx).length > 0 ? ctx : null;
  };

  /* ─── Render a message bubble ─── */
  const appendMessage = (role, text) => {
    const div = document.createElement("div");
    div.className = `assistant-msg assistant-msg--${role}`;
    div.textContent = text;
    $.assistantMessages.appendChild(div);
    $.assistantMessages.scrollTop = $.assistantMessages.scrollHeight;
    return div;
  };

  /* ─── Send question ─── */
  const sendQuestion = (question) => {
    appendMessage("user", question);

    const loadingEl = appendMessage("assistant", "...");
    loadingEl.classList.add("assistant-msg--loading");

    $.assistantInput.disabled = true;
    $.assistantSend.disabled = true;

    const ctx = gatherContext();
    const body = { question };
    if (ctx && ctx.ticker) body.ticker = ctx.ticker;
    if (ctx) body.context = ctx;

    fetch("/agent/ask/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      })
      .then((data) => {
        loadingEl.textContent = data.answer;
        loadingEl.classList.remove("assistant-msg--loading");
      })
      .catch((err) => {
        loadingEl.textContent = `Error: ${err.message}`;
        loadingEl.classList.remove("assistant-msg--loading");
        loadingEl.classList.add("assistant-msg--error");
      })
      .finally(() => {
        $.assistantInput.disabled = false;
        $.assistantSend.disabled = false;
        $.assistantInput.focus();
      });
  };

  /* ─── Form submit ─── */
  $.assistantForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const question = $.assistantInput.value.trim();
    if (!question) return;
    $.assistantInput.value = "";
    sendQuestion(question);
  });
})();
