"""
Contextual Q&A assistant — answers questions about FINA's metrics,
models, and interpretation of analysis results.

Uses litellm for provider-agnostic LLM calls (Ollama local, Anthropic,
OpenAI, etc). The model string in Settings determines the backend:
  - "ollama/mistral"          → local Ollama
  - "anthropic/claude-sonnet-4-6" → Claude API
  - "gpt-4o"                  → OpenAI API

The system prompt contains a compact guide to all FINA metrics and
models; the user prompt injects the current analysis context so
answers are specific to the loaded ticker.
"""

import litellm

from fina.core.config import Settings
from fina.core.exceptions import FetcherError

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True

_SYSTEM_PROMPT = """\
Eres el asistente de FINA, una plataforma de análisis cuantitativo financiero.
Responde en español, de forma concisa (3-5 oraciones máximo).
Sé honesto sobre limitaciones de los modelos.

## Métricas disponibles en FINA

- **Retornos logarítmicos**: r_t = ln(P_t / P_{t-1}). Aditivos en el tiempo.
- **Volatilidad realizada**: Desv. estándar anualizada (×√252).
- **Rolling volatility**: Ventana 21 días, anualizada.
- **Sharpe ratio**: (R̄ − rf) / σ. >1 bueno, >2 excelente, <0 pierde vs libre de riesgo.
- **Sortino ratio**: Como Sharpe pero solo penaliza volatilidad a la baja.
- **Beta**: Sensibilidad vs S&P 500. β=1 se mueve igual, β>1 amplifica, β<1 amortigua.
- **RSI (14d)**: 0-100. >70 sobrecomprado, <30 sobrevendido.
- **MACD**: Cruce de EMAs (12,26,9). Histograma >0 = momentum alcista.
- **Bollinger Bands**: SMA-20 ± 2σ. Precio fuera de bandas = movimiento extremo.

## Modelos cuantitativos

- **GARCH(1,1)**: Modela volatilidad condicional. Persistencia α+β <1 = estacionario. No predice dirección.
- **HMM Gaussiano**: Detecta regímenes (baja/media/alta volatilidad). Retrospectivo, no predictivo.
- **ARIMA (auto)**: Predice retornos. ARIMA(0,0,0) = retornos son ruido blanco (no predecibles).
- **Comparador**: ARIMA vs GARCH lado a lado. Precisión direccional >55% = superior al azar.

## Backtesting

FINA incluye un motor de backtesting completo en el panel "Backtest":
- El usuario define periodos de **entrenamiento** y **prueba** por fecha calendario.
- Se entrenan ARIMA, HMM y GARCH en el periodo de entrenamiento.
- **Señales**: HMM da la dirección base (low_vol→long, mid_vol→hold, high_vol→risk-off). \
ARIMA sobreescribe cuando tiene opinión no-cero. GARCH ajusta el tamaño de posición (target_vol / cond_vol).
- Se simula la estrategia vs benchmark Buy & Hold.
- **Métricas**: retorno total, anualizado, Sharpe, Sortino, max drawdown, Calmar, win rate, information ratio.

## Monte Carlo

FINA incluye simulación Monte Carlo dentro del panel de Backtest:
- Ajusta los modelos una vez en el periodo de entrenamiento.
- Genera **N trayectorias sintéticas** de retornos usando GARCH(1,1) paramétrico (omega, alpha, beta estimados).
- Para cada trayectoria ejecuta la estrategia completa (señales + simulación).
- Agrega resultados en un **fan chart** de percentiles (P5, P25, P50, P75, P95).
- Calcula **VaR 95%** (pérdida máx. en 95% de sims), **CVaR 95%** (expected shortfall), \
**prob. de ganancia** y **prob. de superar Buy & Hold**.
- El usuario puede configurar entre 50 y 1000 simulaciones.

## Validación

Todos los modelos usan split temporal 80/20. GARCH evalúa MAE vs vol realizada. \
ARIMA usa walk-forward 1-step. HMM compara LL/n entre train y test. \
El backtest usa split temporal por fecha (no ratio) para evitar look-ahead bias.

## Reglas

- Si no tienes contexto numérico, responde sobre el software en general.
- No inventes datos. Si no tienes el valor, di que el usuario debe ejecutar el análisis.
- Usa rangos de referencia cuando interpretes (ej: "un Sharpe de 0.8 está por debajo de 1").
- Si el usuario pregunta algo fuera del alcance de FINA, dilo amablemente.
"""


def _build_context_block(context: dict | None) -> str:
    """Build a compact context string from the analysis state."""
    if not context:
        return "No hay análisis cargado actualmente."

    lines = []
    if context.get("ticker"):
        lines.append(f"Ticker: {context['ticker']}")
    if context.get("period"):
        lines.append(f"Período: {context['period']}")

    metric_map = {
        "sharpe": "Sharpe ratio",
        "sortino": "Sortino ratio",
        "beta": "Beta",
        "rsi": "RSI (14d)",
        "volatility": "Vol rolling 21d",
        "annualized_return": "Retorno anualizado",
    }
    for key, label in metric_map.items():
        val = context.get(key)
        if val is not None:
            lines.append(f"{label}: {val}")

    if context.get("garch_persistence") is not None:
        lines.append(f"GARCH persistencia: {context['garch_persistence']}")
    if context.get("hmm_regime"):
        lines.append(f"Régimen HMM actual: {context['hmm_regime']}")
    if context.get("arima_order"):
        lines.append(f"Orden ARIMA: ({','.join(str(x) for x in context['arima_order'])})")
    if context.get("comparison_verdict"):
        lines.append(f"Veredicto comparador: {context['comparison_verdict']}")

    # Backtest context
    if context.get("backtest_sharpe") is not None:
        lines.append(f"Backtest Sharpe: {context['backtest_sharpe']}")
    if context.get("backtest_return") is not None:
        lines.append(f"Backtest retorno total: {context['backtest_return']}")
    if context.get("backtest_max_drawdown") is not None:
        lines.append(f"Backtest max drawdown: {context['backtest_max_drawdown']}")

    # Monte Carlo context
    if context.get("mc_prob_profit") is not None:
        lines.append(f"MC prob. ganancia: {context['mc_prob_profit']}")
    if context.get("mc_var_95") is not None:
        lines.append(f"MC VaR 95%: {context['mc_var_95']}")
    if context.get("mc_prob_beat_bh") is not None:
        lines.append(f"MC prob. superar B&H: {context['mc_prob_beat_bh']}")

    return "\n".join(lines) if lines else "No hay análisis cargado actualmente."


def answer_question(
    question: str,
    context: dict | None,
    settings: Settings,
) -> str:
    """
    Answer a user question about FINA's metrics or model results.

    Uses litellm to call the configured model (local Ollama or cloud API).

    Args:
        question: The user's question in natural language.
        context:  Optional dict with current analysis state.
        settings: Application settings (LLM provider config).

    Returns:
        Answer string from the LLM.

    Raises:
        FetcherError: If the LLM call fails for any reason.
    """
    context_block = _build_context_block(context)

    user_prompt = (
        f"## Contexto del análisis actual\n{context_block}\n\n"
        f"## Pregunta del usuario\n{question}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # Build litellm model string from settings
    model = f"ollama/{settings.ollama_model}"

    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            api_base=settings.ollama_base_url,
            max_tokens=512,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        raise FetcherError(
            f"Assistant LLM call failed: {exc}"
        ) from exc
