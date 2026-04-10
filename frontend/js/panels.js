/* ============================================================
   FINA — Panel Rendering & Event Handlers
   ============================================================ */

(() => {
  "use strict";

  const F = window.FINA;
  const state = F.state;
  const $ = F.$;
  const show = F.show;
  const hide = F.hide;
  const fmt = F.fmt;
  const fmtPct = F.fmtPct;
  const fmtSign = F.fmtSign;
  const sentiment = F.sentiment;
  const escHtml = F.escHtml;

  /* ─── Overview rendering ─── */
  const renderOverview = () => {
    const data = state.analysisResult.data;
    const computed = data.computed || {};
    const warnings = computed.warnings || [];

    $.resultsTicker.textContent = data.ticker;
    $.resultsPeriod.textContent = data.period.toUpperCase();
    const timeParts = [new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })];
    if (state.processTimeMs) timeParts.push(`${parseFloat(state.processTimeMs).toFixed(0)}ms`);
    const obs = computed.returns ? computed.returns.observations : null;
    if (obs) timeParts.push(`${fmt(obs, 0)} obs`);
    $.resultsTime.textContent = timeParts.join(" · ");
    document.title = `FINA — ${data.ticker}`;

    const cards = buildMetricCards(computed);
    $.metricsGrid.innerHTML = "";
    cards.forEach((card) => { $.metricsGrid.appendChild(card); });

    if (warnings.length > 0) {
      $.warningsInner.innerHTML = warnings.map((w) =>
        `<div class="warning-item"><span class="warning-icon">!</span><span>${escHtml(w)}</span></div>`
      ).join("");
      show($.warnings);
    } else {
      hide($.warnings);
    }

    // Fetch fundamentals
    fetchFundamentals(data.ticker);
  };

  const fetchFundamentals = (ticker) => {
    hide($.fundamentalsSection);

    fetch(`/fundamentals/${encodeURIComponent(ticker)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data || !data.fundamentals) return;
        state.fundamentalsResult = data.fundamentals;
        renderFundamentals(data.fundamentals);
      })
      .catch(() => { /* silently skip if fundamentals unavailable */ });
  };

  const renderFundamentals = (f) => {
    const fmtMoney = (v) => {
      if (v === null || v === undefined) return "N/A";
      if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
      if (v >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
      if (v >= 1e6)  return `$${(v / 1e6).toFixed(0)}M`;
      return `$${v.toLocaleString()}`;
    };

    const items = [
      { label: "Empresa",       value: f.company_name,                    format: (v) => v || "N/A" },
      { label: "Sector",        value: f.sector,                          format: (v) => v || "N/A" },
      { label: "Market Cap",    value: f.market_cap,                      format: fmtMoney },
      { label: "EPS (TTM)",     value: f.eps,                             format: (v) => v != null ? `$${Number(v).toFixed(2)}` : "N/A" },
      { label: "EPS Forward",   value: f.forward_eps,                     format: (v) => v != null ? `$${Number(v).toFixed(2)}` : "N/A" },
      { label: "EPS Growth",    value: f.eps_growth,                      format: (v) => v != null ? fmtSign(v) : "N/A" },
      { label: "P/E (TTM)",     value: f.pe_ratio,                        format: (v) => v != null ? fmt(v, 1) : "N/A" },
      { label: "P/E Forward",   value: f.forward_pe,                      format: (v) => v != null ? fmt(v, 1) : "N/A" },
      { label: "P/B",           value: f.price_to_book,                   format: (v) => v != null ? fmt(v, 2) : "N/A" },
      { label: "Margen neto",   value: f.profit_margin,                   format: (v) => v != null ? fmtPct(v) : "N/A" },
      { label: "Margen bruto",  value: f.gross_margin,                    format: (v) => v != null ? fmtPct(v) : "N/A" },
      { label: "Margen oper.",  value: f.operating_margin,                format: (v) => v != null ? fmtPct(v) : "N/A" },
      { label: "D/E",           value: f.debt_to_equity,                  format: (v) => v != null ? fmt(v, 2) : "N/A" },
      { label: "Current Ratio", value: f.current_ratio,                   format: (v) => v != null ? fmt(v, 2) : "N/A" },
      { label: "ROE",           value: f.roe,                             format: (v) => v != null ? fmtPct(v) : "N/A" },
      { label: "ROA",           value: f.roa,                             format: (v) => v != null ? fmtPct(v) : "N/A" },
      { label: "Rev. Growth",   value: f.revenue_growth,                  format: (v) => v != null ? fmtSign(v) : "N/A" },
      { label: "Div. Yield",    value: f.dividend_yield,                  format: (v) => v != null ? fmtPct(v) : "N/A" },
    ];

    // Only show items that have data
    const available = items.filter((i) => i.value !== null && i.value !== undefined);
    if (available.length === 0) return;

    $.fundamentalsGrid.innerHTML = available.map((i) => {
      const val = i.format(i.value);
      return `<div class="fund-card"><div class="fund-label">${escHtml(i.label)}</div><div class="fund-value">${escHtml(val)}</div></div>`;
    }).join("");

    show($.fundamentalsSection);
  };

  const buildMetricCards = (computed) => {
    const defs = [
      {
        label: "Retorno anualiz.",
        value: (c) => c.returns ? fmtSign(c.returns.mean * 252) : "N/A",
        detail: (c) => c.returns ? `${fmt(c.returns.observations, 0)} obs` : "",
        color: (c) => c.returns ? sentiment(c.returns.mean) : "na",
      },
      {
        label: "Volatilidad 21d",
        value: (c) => c.rolling_volatility ? fmtPct(c.rolling_volatility.latest_sd) : "N/A",
        detail: (c) => c.rolling_volatility ? `ventana ${c.rolling_volatility.window}d` : "",
        color: () => "neutral",
      },
      {
        label: "Sharpe",
        value: (c) => c.sharpe ? fmt(c.sharpe.sharpe_ratio) : "N/A",
        detail: (c) => c.sharpe ? `rf ${fmtPct(c.sharpe.risk_free_rate)}` : "",
        color: (c) => c.sharpe ? sentiment(c.sharpe.sharpe_ratio) : "na",
      },
      {
        label: "Beta",
        value: (c) => c.beta ? fmt(c.beta.beta) : "N/A",
        detail: (c) => c.beta ? `vs ${c.beta.benchmark}` : "",
        color: () => "neutral",
      },
      {
        label: "Sortino",
        value: (c) => c.sortino ? fmt(c.sortino.sortino_ratio) : "N/A",
        detail: (c) => c.sortino ? `${c.sortino.downside_observations} obs bajistas` : "Sin datos bajistas",
        color: (c) => c.sortino ? sentiment(c.sortino.sortino_ratio) : "na",
      },
      {
        label: "Max Drawdown",
        value: (c) => c.returns ? fmtSign(c.returns.min) : "N/A",
        detail: () => "peor retorno diario",
        color: (c) => c.returns ? "negative" : "na",
      },
      {
        label: "RSI",
        value: (c) => c.rsi ? fmt(c.rsi.latest, 1) : "N/A",
        detail: (c) => {
          if (!c.rsi) return "";
          const v = c.rsi.latest;
          return v > 70 ? "Sobrecomprado" : v < 30 ? "Sobrevendido" : "Neutral";
        },
        color: (c) => {
          if (!c.rsi) return "na";
          const v = c.rsi.latest;
          return v > 70 ? "negative" : v < 30 ? "positive" : "neutral";
        },
      },
      {
        label: "MACD Histograma",
        value: (c) => c.macd ? fmt(c.macd.histogram, 3) : "N/A",
        detail: (c) => c.macd ? (c.macd.histogram >= 0 ? "Momentum alcista" : "Momentum bajista") : "",
        color: (c) => c.macd ? sentiment(c.macd.histogram) : "na",
      },
    ];

    return defs.map((def) => {
      const div = document.createElement("div");
      div.className = "metric-card";
      const val    = def.value(computed);
      const detail = def.detail(computed);
      const clr    = def.color(computed);
      const arrow  = clr === "positive" ? "&#x25B2;" : clr === "negative" ? "&#x25BC;" : "";
      div.innerHTML =
        `<div class="mc-label">${escHtml(def.label)}</div>` +
        `<div class="mc-value ${clr}">` +
          (arrow ? `<span class="mc-arrow">${arrow}</span> ` : "") +
          escHtml(val) +
        "</div>" +
        (detail ? `<div class="mc-detail">${escHtml(detail)}</div>` : "");
      return div;
    });
  };

  /* ─── Agent / News ─── */
  const renderAgentResults = () => {
    if (state.agentTicker) {
      $.newsPanelTicker.textContent = state.agentTicker;
      $.newsPanelMeta.textContent = "Noticias & Análisis IA";
    }

    if (!state.agentResult) {
      $.summaryBody.innerHTML = '<div class="summary-error">Resumen IA no disponible.</div>';
      $.summaryStatus.textContent = "error";
      show($.newsSummarySection);
      hide($.newsPanelEmpty);
      return;
    }
    $.summaryBody.innerHTML = `<div class="summary-text">${escHtml(state.agentResult.summary)}</div>`;
    $.summaryStatus.textContent = "";
    show($.newsSummarySection);
    hide($.newsPanelEmpty);
    if (state.agentResult.headlines && state.agentResult.headlines.length > 0) {
      $.headlinesList.innerHTML = state.agentResult.headlines.map((h) =>
        `<li class="headline-item">${escHtml(h)}</li>`
      ).join("");
      show($.headlinesSection);
    }
  };

  /* ─── Metrics Panel ─── */
  const loadMetricsPanel = () => {
    const data = state.analysisResult.data;
    $.metricsPanelTicker.textContent = data.ticker;
    $.metricsPanelMeta.textContent   = data.period.toUpperCase();

    if (state.timeseriesResult &&
        state.timeseriesResult.ticker === state.ticker &&
        state.timeseriesResult.period === state.period) {
      renderMetricsPanel();
      return;
    }

    hide($.metricsPanelContent);
    hide($.metricsPanelError);
    show($.metricsPanelLoading);

    fetch("/analysis/timeseries/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: state.ticker,
        period: state.period,
        series: ["prices", "rolling_volatility", "bollinger", "volume", "ohlc"],
      }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      })
      .then((data) => {
        state.timeseriesResult = data;
        hide($.metricsPanelLoading);
        renderMetricsPanel();
      })
      .catch((err) => {
        hide($.metricsPanelLoading);
        $.metricsPanelErrorMsg.textContent = `No se pudo cargar la serie de tiempo: ${err.message}`;
        show($.metricsPanelError);
      });
  };

  const renderMetricsPanel = () => {
    const computed = state.analysisResult.data.computed || {};
    const series   = (state.timeseriesResult && state.timeseriesResult.series) || {};

    show($.metricsPanelContent);
    F.clearPins("metrics");

    F.renderPriceChart(series.ohlc || [], series.bollinger || [], series.prices || []);
    F.renderVolChart(series.rolling_volatility || [], computed);
    renderReturnsStats(computed);
    renderRatios(computed);
    F.renderBollingerChart(series.bollinger || [], computed);
    F.renderVolumeChart(series.volume || []);

    F.initPinGroup("metrics");
  };

  /* ─── Returns stats table ─── */
  const renderReturnsStats = (computed) => {
    const r = computed.returns;
    if (!r) { $.returnsStatsGrid.innerHTML = '<p class="mc-detail">No disponible</p>'; return; }

    const rows = [
      { label: "Media diaria",   value: fmtSign(r.mean, 3),             cls: sentiment(r.mean) },
      { label: "Desv. estándar", value: fmtPct(r.std),                  cls: "neutral" },
      { label: "Mínimo",         value: fmtSign(r.min),                 cls: "negative" },
      { label: "Máximo",         value: fmtSign(r.max),                 cls: "positive" },
      { label: "Observaciones",  value: `${fmt(r.observations, 0)} días`, cls: "neutral" },
      { label: "Método",         value: r.method || "log",              cls: "neutral" },
    ];

    $.returnsStatsGrid.innerHTML = rows.map((row) =>
      `<div class="return-stat-row">` +
        `<div class="return-stat-label">${escHtml(row.label)}</div>` +
        `<div class="return-stat-value ${row.cls}">${escHtml(row.value)}</div>` +
      `</div>`
    ).join("");
  };

  /* ─── Ratios table ─── */
  const renderRatios = (computed) => {
    const rows = [
      {
        label: "Sharpe",
        value: computed.sharpe ? fmt(computed.sharpe.sharpe_ratio) : "N/A",
        detail: computed.sharpe ? `rf ${fmtPct(computed.sharpe.risk_free_rate)}` : "",
        cls: computed.sharpe ? sentiment(computed.sharpe.sharpe_ratio) : "na",
      },
      {
        label: "Sortino",
        value: computed.sortino ? fmt(computed.sortino.sortino_ratio) : "N/A",
        detail: computed.sortino ? `${computed.sortino.downside_observations} obs bajistas` : "Sin datos bajistas",
        cls: computed.sortino ? sentiment(computed.sortino.sortino_ratio) : "na",
      },
      {
        label: "Beta",
        value: computed.beta ? fmt(computed.beta.beta) : "N/A",
        detail: computed.beta ? `vs ${computed.beta.benchmark} · R²=${fmt(computed.beta.r_squared)}` : "",
        cls: "neutral",
      },
      {
        label: "Correlación",
        value: computed.beta ? fmt(computed.beta.correlation) : "N/A",
        detail: computed.beta ? `con ${computed.beta.benchmark}` : "",
        cls: "neutral",
      },
      {
        label: "Volatilidad anual",
        value: computed.volatility ? fmtPct(computed.volatility["volatility(s.d.)"]) : "N/A",
        detail: computed.volatility ? `${fmt(computed.volatility.observations, 0)} obs` : "",
        cls: "neutral",
      },
    ];

    $.ratiosGrid.innerHTML = rows.map((row) =>
      `<div class="ratio-row">` +
        `<div>` +
          `<div class="ratio-label">${escHtml(row.label)}</div>` +
          (row.detail ? `<div class="ratio-detail">${escHtml(row.detail)}</div>` : "") +
        `</div>` +
        `<div class="ratio-value ${row.cls}">${escHtml(row.value)}</div>` +
      `</div>`
    ).join("");
  };

  /* ─── Technicals Panel ─── */
  const loadTechnicalsPanel = () => {
    const data = state.analysisResult.data;
    $.techPanelTicker.textContent = data.ticker;
    $.techPanelMeta.textContent   = `${data.period.toUpperCase()} · Indicadores técnicos`;

    if (state.techSeriesResult &&
        state.techSeriesResult.ticker === state.ticker &&
        state.techSeriesResult.period === state.period) {
      renderTechnicalsPanel();
      return;
    }

    hide($.techPanelContent);
    hide($.techPanelError);
    show($.techPanelLoading);

    fetch("/analysis/timeseries/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: state.ticker,
        period: state.period,
        series: ["rsi", "macd", "bollinger"],
      }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      })
      .then((data) => {
        state.techSeriesResult = data;
        hide($.techPanelLoading);
        renderTechnicalsPanel();
      })
      .catch((err) => {
        hide($.techPanelLoading);
        $.techPanelErrorMsg.textContent = `No se pudo cargar indicadores: ${err.message}`;
        show($.techPanelError);
      });
  };

  const renderTechnicalsPanel = () => {
    const series = (state.techSeriesResult && state.techSeriesResult.series) || {};
    const computed = (state.analysisResult && state.analysisResult.data.computed) || {};
    show($.techPanelContent);
    F.clearPins("technicals");
    F.renderRsiChart(series.rsi || [], computed);
    F.renderMacdChart(series.macd || []);
    F.renderTechBollingerChart(series.bollinger || [], computed);
    F.initPinGroup("technicals");
  };

  /* ─── Models Panel ─── */
  const loadModelsPanel = () => {
    const data = state.analysisResult.data;
    $.modelsPanelTicker.textContent = data.ticker;
    $.modelsPanelMeta.textContent = `${data.period.toUpperCase()} · GARCH + HMM + ARIMA`;

    /* Use cache if same ticker/period */
    if (state.modelsResult &&
        state.modelsResult.ticker === state.ticker &&
        state.modelsResult.period === state.period) {
      renderModelsPanel();
      return;
    }

    hide($.modelsPanelContent);
    hide($.modelsPanelError);
    hide($.modelsPanelEmpty);
    show($.modelsPanelLoading);

    const body = JSON.stringify({ ticker: state.ticker, period: state.period });
    const headers = { "Content-Type": "application/json" };

    /* Fetch scalar + timeseries + comparison in parallel */
    const p1 = fetch("/models/", { method: "POST", headers, body })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      });

    const p2 = fetch("/models/timeseries/", { method: "POST", headers, body })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      });

    const p3 = fetch("/models/compare/", { method: "POST", headers, body })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      });

    Promise.all([p1, p2, p3])
      .then(([models, timeseries, comparison]) => {
        state.modelsResult = models;
        state.modelsTimeseriesResult = timeseries;
        state.comparisonResult = comparison;
        hide($.modelsPanelLoading);
        renderModelsPanel();
      })
      .catch((err) => {
        hide($.modelsPanelLoading);
        $.modelsPanelErrorMsg.textContent = `No se pudo cargar modelos: ${err.message}`;
        show($.modelsPanelError);
      });
  };

  /* ── Shared diagnostics renderer ── */
  const renderDiagBlock = (title, rows) =>
    `<div class="diag-section-title">${escHtml(title)}</div>` +
    `<div class="diag-grid">${rows.map((row) =>
      `<div class="diag-row">` +
        `<div class="diag-left">` +
          `<div class="diag-label">${escHtml(row.label)}</div>` +
          (row.detail ? `<div class="diag-detail">${escHtml(row.detail)}</div>` : "") +
        `</div>` +
        `<div class="diag-value ${row.cls || ""}">${escHtml(row.value)}</div>` +
      `</div>`
    ).join("")}</div>`;

  const renderModelsPanel = () => {
    const m = state.modelsResult;
    const ts = state.modelsTimeseriesResult;
    if (!m) return;

    show($.modelsPanelContent);

    /* ── HMM Current Regime Badge ── */
    if (m.hmm && m.hmm.current_regime) {
      const regime = m.hmm.current_regime;
      const colors = F.REGIME_COLORS || {};
      $.regimeDot.style.background = colors[regime.label] || "#586064";
      $.regimeLabel.textContent = regime.label_es;
      $.regimeDetail.textContent = `${regime.duration_days} días · desde ${regime.since_date}`;
      F.show($.regimeBadge);
    } else {
      F.hide($.regimeBadge);
    }

    /* ── HMM Regime Timeline ── */
    F.renderHmmRegimesChart(ts ? ts.hmm_states : []);

    /* ── HMM Distributions Chart ── */
    F.renderHmmDistributionsChart(m.hmm ? m.hmm.distributions : null);

    /* ── HMM State Parameters ── */
    if (m.hmm && m.hmm.state_params) {
      let paramsHtml = '<div class="state-params-grid">';
      m.hmm.state_params.forEach((sp) => {
        const color = (F.REGIME_COLORS || {})[sp.label] || "#586064";
        paramsHtml +=
          `<div class="state-param-card">` +
            `<div class="sp-header">` +
              `<span class="sp-dot" style="background:${color}"></span>` +
              `<span class="sp-name">${escHtml(sp.label_es)}</span>` +
            `</div>` +
            `<div class="sp-rows">` +
              `<div class="sp-row"><span class="sp-label">Media diaria</span><span class="sp-value ${sentiment(sp.mean_return)}">${fmtSign(sp.mean_return, 3)}</span></div>` +
              `<div class="sp-row"><span class="sp-label">Vol anualizada</span><span class="sp-value">${fmtPct(sp.annualized_vol)}</span></div>` +
              `<div class="sp-row"><span class="sp-label">Prob estacionaria</span><span class="sp-value">${fmtPct(sp.stationary_prob)}</span></div>` +
            `</div>` +
          `</div>`;
      });
      paramsHtml += '</div>';
      $.modelsStateParams.innerHTML = paramsHtml;
    } else {
      $.modelsStateParams.innerHTML = '<p class="mc-detail">HMM no disponible</p>';
    }

    /* ── HMM Validation (train/test) ── */
    if (m.hmm && m.hmm.split) {
      const sp = m.hmm.split;
      const trainScore = m.hmm.train_score;
      const testScore = m.hmm.test_score;
      const delta = testScore - trainScore;
      const deltaCls = Math.abs(delta) < 0.5 ? "positive" : (delta < -1.0 ? "negative" : "");
      const deltaLabel = Math.abs(delta) < 0.5 ? "Buen ajuste" : (delta < -1.0 ? "Posible sobreajuste" : "Aceptable");

      $.modelsValidation.innerHTML =
        `<div class="validation-grid">` +
          `<div class="val-row">` +
            `<div class="val-label">Split</div>` +
            `<div class="val-value">${Math.round(sp.train_ratio * 100)}/${Math.round((1 - sp.train_ratio) * 100)}</div>` +
          `</div>` +
          `<div class="val-row">` +
            `<div class="val-label">Train</div>` +
            `<div class="val-value">${sp.train_size} obs</div>` +
          `</div>` +
          `<div class="val-row">` +
            `<div class="val-label">Test</div>` +
            `<div class="val-value">${sp.test_size} obs</div>` +
          `</div>` +
          `<div class="val-divider"></div>` +
          `<div class="val-row">` +
            `<div class="val-label">LL/n train</div>` +
            `<div class="val-value">${fmt(trainScore, 3)}</div>` +
          `</div>` +
          `<div class="val-row">` +
            `<div class="val-label">LL/n test</div>` +
            `<div class="val-value">${fmt(testScore, 3)}</div>` +
          `</div>` +
          `<div class="val-row">` +
            `<div class="val-label">Δ (test − train)</div>` +
            `<div class="val-value ${deltaCls}">${delta >= 0 ? "+" : ""}${fmt(delta, 3)}</div>` +
          `</div>` +
          `<div class="val-row">` +
            `<div class="val-label">Diagnóstico</div>` +
            `<div class="val-value ${deltaCls}">${escHtml(deltaLabel)}</div>` +
          `</div>` +
          `<div class="val-divider"></div>` +
          `<div class="val-row">` +
            `<div class="val-label">AIC</div>` +
            `<div class="val-value">${fmt(m.hmm.aic, 1)}</div>` +
          `</div>` +
          `<div class="val-row">` +
            `<div class="val-label">BIC</div>` +
            `<div class="val-value">${fmt(m.hmm.bic, 1)}</div>` +
          `</div>` +
        `</div>`;
    } else {
      $.modelsValidation.innerHTML = '<p class="mc-detail">Validación no disponible</p>';
    }

    /* ── GARCH Conditional Volatility ── */
    F.renderGarchVolChart(ts ? ts.garch_vol : []);

    /* ── GARCH Forecast ── */
    const forecast = m.garch ? m.garch.forecast : [];
    const confidence = m.garch ? m.garch.confidence : 0.95;
    F.renderGarchForecastChart(forecast, confidence);

    /* ── GARCH Diagnostics + Validation ── */
    if (m.garch && m.garch.diagnostics) {
      const d = m.garch.diagnostics;
      const tsG = m.garch.test_score || {};
      const spG = m.garch.split || {};
      const persistCls = d.persistence > 0.99 ? "negative" : d.persistence > 0.95 ? "" : "positive";

      let maeCls = "";
      let maeDiag = "";
      if (tsG.mae !== null && tsG.realized_vol !== null && tsG.realized_vol > 0) {
        const maeRatio = tsG.mae / tsG.realized_vol;
        if (maeRatio < 0.5) { maeCls = "positive"; maeDiag = "Buen ajuste"; }
        else if (maeRatio < 1.0) { maeCls = ""; maeDiag = "Aceptable"; }
        else { maeCls = "negative"; maeDiag = "Posible sobreajuste"; }
      }

      const diagRows = [
        { label: "α (alpha)", value: fmt(d.alpha, 4), detail: "Impacto de shocks recientes" },
        { label: "β (beta)", value: fmt(d.beta, 4), detail: "Persistencia de la volatilidad" },
        { label: "Persistencia (α+β)", value: fmt(d.persistence, 4), cls: persistCls, detail: d.persistence >= 1 ? "No estacionario" : "Estacionario" },
        { label: "Vol largo plazo", value: d.long_run_vol !== null ? fmtPct(d.long_run_vol) : "N/A", detail: "Volatilidad incondicional" },
      ];

      const validRows = [
        { label: "Split", value: `${Math.round((spG.train_ratio || 0.8) * 100)}/${Math.round((1 - (spG.train_ratio || 0.8)) * 100)}`, detail: `${spG.train_size || "?"} train · ${spG.test_size || "?"} test` },
        { label: "MAE out-of-sample", value: tsG.mae !== null ? `${fmt(tsG.mae * 100, 3)}%` : "N/A", cls: maeCls, detail: maeDiag },
        { label: "RMSE out-of-sample", value: tsG.rmse !== null ? `${fmt(tsG.rmse * 100, 3)}%` : "N/A", detail: "" },
        { label: "Vol realizada (test)", value: tsG.realized_vol !== null ? `${fmt(tsG.realized_vol * 100, 3)}%` : "N/A", detail: "Media |r| en test set" },
        { label: "AIC (full)", value: fmt(d.aic, 1), detail: "" },
        { label: "BIC (full)", value: fmt(d.bic, 1), detail: "" },
      ];

      $.modelsDiagnostics.innerHTML =
        renderDiagBlock("Parámetros", diagRows) +
        renderDiagBlock("Validación", validRows);
    } else {
      $.modelsDiagnostics.innerHTML = '<p class="mc-detail">GARCH no disponible</p>';
    }

    /* ── ARIMA Diagnostics ── */
    if (m.arima && m.arima.diagnostics) {
      const ad = m.arima.diagnostics;
      const at = m.arima.test_score || {};
      const as = m.arima.split || {};
      const orderStr = `(${(ad.order || [0,0,0]).join(",")})`;
      $.arimaDiagSubtitle.textContent = `ARIMA${orderStr} · selección por AIC`;

      let lbCls = "";
      let lbDiag = "";
      if (ad.ljung_box_pvalue !== null && ad.ljung_box_pvalue !== undefined) {
        if (ad.ljung_box_pvalue > 0.05) { lbCls = "positive"; lbDiag = "Sin autocorrelación"; }
        else { lbCls = "negative"; lbDiag = "Autocorrelación residual"; }
      }

      let dirAccStr = "N/A";
      let dirAccCls = "";
      let dirAccDiag = "";
      if (at.directional_accuracy !== null && at.directional_accuracy !== undefined) {
        dirAccStr = fmtPct(at.directional_accuracy);
        if (at.directional_accuracy > 0.55) { dirAccCls = "positive"; dirAccDiag = "Superior al azar"; }
        else if (at.directional_accuracy > 0.45) { dirAccCls = ""; dirAccDiag = "Cercano al azar"; }
        else { dirAccCls = "negative"; dirAccDiag = "Inferior al azar"; }
      } else {
        dirAccDiag = "Sin opinión direccional";
      }

      const arimaParamRows = [
        { label: "Orden (p,d,q)", value: orderStr, detail: "Selección automática por AIC" },
        { label: "AIC", value: fmt(ad.aic, 1), detail: "" },
        { label: "BIC", value: fmt(ad.bic, 1), detail: "" },
        { label: "Ljung-Box p-value", value: ad.ljung_box_pvalue !== null ? fmt(ad.ljung_box_pvalue, 4) : "N/A", cls: lbCls, detail: lbDiag },
      ];

      const arimaValidRows = [
        { label: "Split", value: `${Math.round((as.train_ratio || 0.8) * 100)}/${Math.round((1 - (as.train_ratio || 0.8)) * 100)}`, detail: `${as.train_size || "?"} train · ${as.test_size || "?"} test` },
        { label: "MAE out-of-sample", value: at.mae !== null && at.mae !== undefined ? `${fmt(at.mae * 100, 3)}%` : "N/A", detail: "" },
        { label: "RMSE out-of-sample", value: at.rmse !== null && at.rmse !== undefined ? `${fmt(at.rmse * 100, 3)}%` : "N/A", detail: "" },
        { label: "Precisión direccional", value: dirAccStr, cls: dirAccCls, detail: dirAccDiag },
        { label: "Muestras evaluadas", value: at.n_samples ? fmt(at.n_samples, 0) : "N/A", detail: "Walk-forward 1-step" },
      ];

      $.arimaDiagnostics.innerHTML =
        renderDiagBlock("Parámetros", arimaParamRows) +
        renderDiagBlock("Validación", arimaValidRows);
    } else {
      $.arimaDiagnostics.innerHTML = '<p class="mc-detail">ARIMA no disponible</p>';
      $.arimaDiagSubtitle.textContent = "Auto-ARIMA · selección por AIC";
    }

    /* ── Model Comparison Table ── */
    const comp = state.comparisonResult;
    if (comp && comp.comparison && comp.comparison.length > 0) {
      let tableHtml =
        `<table class="comparison-tbl">` +
        `<thead><tr>` +
          `<th>Métrica</th>` +
          `<th>ARIMA</th>` +
          `<th>GARCH(1,1)</th>` +
        `</tr></thead><tbody>`;

      comp.comparison.forEach((row) => {
        const aClass = row.winner === "arima" ? "winner" : "";
        const gClass = row.winner === "garch" ? "winner" : "";
        tableHtml +=
          `<tr>` +
            `<td class="cmp-label">${escHtml(row.label)}</td>` +
            `<td class="cmp-val ${aClass}">${escHtml(row.arima)}</td>` +
            `<td class="cmp-val ${gClass}">${escHtml(row.garch)}</td>` +
          `</tr>`;
      });

      tableHtml += `</tbody></table>`;
      $.comparisonTable.innerHTML = tableHtml;

      /* ── Verdict ── */
      if (comp.verdict) {
        const v = comp.verdict;
        const verdictIcon = v.best_forecast === "none" ? "○" : v.best_forecast === "arima" ? "▲" : "—";
        const volIcon = v.best_volatility === "garch" ? "▲" : v.best_volatility === "unstable" ? "!" : "—";

        $.comparisonVerdict.innerHTML =
          `<div class="verdict-row">` +
            `<span class="verdict-icon">${verdictIcon}</span>` +
            `<div class="verdict-text">` +
              `<div class="verdict-title">Pronóstico de retornos</div>` +
              `<div class="verdict-detail">${escHtml(v.forecast_reason)}</div>` +
            `</div>` +
          `</div>` +
          `<div class="verdict-row">` +
            `<span class="verdict-icon">${volIcon}</span>` +
            `<div class="verdict-text">` +
              `<div class="verdict-title">Pronóstico de volatilidad</div>` +
              `<div class="verdict-detail">${escHtml(v.volatility_reason)}</div>` +
            `</div>` +
          `</div>`;
      }
    } else {
      $.comparisonTable.innerHTML = '<p class="mc-detail">Comparación no disponible</p>';
      $.comparisonVerdict.innerHTML = '';
    }

    /* ── Warnings ── */
    const allWarnings = (m.warnings || []).concat(ts ? (ts.warnings || []) : []);
    if (allWarnings.length) {
      $.modelsWarningsInner.innerHTML = allWarnings.map((w) =>
        `<div class="warning-item"><span class="warning-icon">!</span><span>${escHtml(w)}</span></div>`
      ).join("");
      F.show($.modelsWarnings);
    } else {
      F.hide($.modelsWarnings);
    }
  };

  /* ─── Expose ─── */
  F.renderOverview = renderOverview;
  F.renderAgentResults = renderAgentResults;
  F.loadMetricsPanel = loadMetricsPanel;
  F.loadTechnicalsPanel = loadTechnicalsPanel;
  F.loadModelsPanel = loadModelsPanel;

  /* ─── Event Handlers ─── */
  $.railLinks.forEach((link) => {
    link.addEventListener("click", () => {
      if (link.disabled) return;
      F.switchToPanel(link.dataset.panel);
    });
  });

  $.analyzeBtn.addEventListener("click", F.runAnalysis);

  $.ticker.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); F.runAnalysis(); }
  });

  $.ticker.addEventListener("input", F.validateTicker);

  $.period.addEventListener("change", () => { state.period = $.period.value; });

  $.paramsToggle.addEventListener("click", () => {
    const expanded = $.paramsToggle.getAttribute("aria-expanded") === "true";
    $.paramsToggle.setAttribute("aria-expanded", String(!expanded));
    $.paramsBody.classList.toggle("collapsed", expanded);
  });

  $.errorRetry.addEventListener("click", F.runAnalysis);

  /* Price chart toggle (candle / line) */
  document.querySelectorAll("#price-chart-toggle .toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode;
      if (mode === F.getPriceChartMode()) return;
      F.setPriceChartMode(mode);
      document.querySelectorAll("#price-chart-toggle .toggle-btn").forEach((b) => {
        b.classList.toggle("toggle-btn--active", b.dataset.mode === mode);
      });
      const series = (state.timeseriesResult && state.timeseriesResult.series) || {};
      if (series.ohlc || series.bollinger || series.prices) {
        F.renderPriceChart(series.ohlc || [], series.bollinger || [], series.prices || []);
      }
    });
  });

  /* Empty state chip clicks */
  document.querySelectorAll(".empty-chip[data-ticker]").forEach((chip) => {
    chip.addEventListener("click", () => {
      $.ticker.value = chip.dataset.ticker;
      F.runAnalysis();
    });
  });

  /* Double-click on any chart canvas resets zoom */
  document.querySelectorAll("canvas[id^='chart-']").forEach((canvas) => {
    canvas.addEventListener("dblclick", () => {
      const chartInstance = Chart.getChart(canvas);
      if (!chartInstance) return;
      if (chartInstance.scales.y) {
        delete chartInstance.scales.y.options.min;
        delete chartInstance.scales.y.options.max;
      }
      if (chartInstance.resetZoom) chartInstance.resetZoom();
    });
  });

  /* ─── Pin clear buttons ─── */
  $.pinClearTech.addEventListener("click", () => F.clearPins("technicals"));
  $.pinClearMetrics.addEventListener("click", () => F.clearPins("metrics"));

  /* ─── Init ─── */
  $.ticker.focus();
  F.checkHealth();
  setInterval(F.checkHealth, 30000);
})();
