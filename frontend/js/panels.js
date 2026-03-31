/* ============================================================
   FINA — Panel Rendering & Event Handlers
   ============================================================ */

(function () {
  "use strict";

  var F = window.FINA;
  var state = F.state;
  var $ = F.$;
  var show = F.show;
  var hide = F.hide;
  var fmt = F.fmt;
  var fmtPct = F.fmtPct;
  var fmtSign = F.fmtSign;
  var sentiment = F.sentiment;
  var escHtml = F.escHtml;

  /* ─── Overview rendering ─── */
  function renderOverview() {
    var data = state.analysisResult.data;
    var computed = data.computed || {};
    var warnings = computed.warnings || [];

    $.resultsTicker.textContent = data.ticker;
    $.resultsPeriod.textContent = data.period.toUpperCase();
    var timeParts = [new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })];
    if (state.processTimeMs) timeParts.push(parseFloat(state.processTimeMs).toFixed(0) + "ms");
    var obs = computed.returns ? computed.returns.observations : null;
    if (obs) timeParts.push(fmt(obs, 0) + " obs");
    $.resultsTime.textContent = timeParts.join(" · ");
    document.title = "FINA — " + data.ticker;

    var cards = buildMetricCards(computed);
    $.metricsGrid.innerHTML = "";
    cards.forEach(function (card) { $.metricsGrid.appendChild(card); });

    if (warnings.length > 0) {
      $.warningsInner.innerHTML = warnings.map(function (w) {
        return '<div class="warning-item"><span class="warning-icon">!</span><span>' + escHtml(w) + "</span></div>";
      }).join("");
      show($.warnings);
    } else {
      hide($.warnings);
    }
  }

  function buildMetricCards(computed) {
    var defs = [
      {
        label: "Retorno anualiz.",
        value: function (c) { return c.returns ? fmtSign(c.returns.mean * 252) : "N/A"; },
        detail: function (c) { return c.returns ? fmt(c.returns.observations, 0) + " obs" : ""; },
        color: function (c) { return c.returns ? sentiment(c.returns.mean) : "na"; },
      },
      {
        label: "Volatilidad 21d",
        value: function (c) { return c.rolling_volatility ? fmtPct(c.rolling_volatility.latest_sd) : "N/A"; },
        detail: function (c) { return c.rolling_volatility ? "ventana " + c.rolling_volatility.window + "d" : ""; },
        color: function () { return "neutral"; },
      },
      {
        label: "Sharpe",
        value: function (c) { return c.sharpe ? fmt(c.sharpe.sharpe_ratio) : "N/A"; },
        detail: function (c) { return c.sharpe ? "rf " + fmtPct(c.sharpe.risk_free_rate) : ""; },
        color: function (c) { return c.sharpe ? sentiment(c.sharpe.sharpe_ratio) : "na"; },
      },
      {
        label: "Beta",
        value: function (c) { return c.beta ? fmt(c.beta.beta) : "N/A"; },
        detail: function (c) { return c.beta ? "vs " + c.beta.benchmark : ""; },
        color: function () { return "neutral"; },
      },
      {
        label: "Sortino",
        value: function (c) { return c.sortino ? fmt(c.sortino.sortino_ratio) : "N/A"; },
        detail: function (c) { return c.sortino ? c.sortino.downside_observations + " obs bajistas" : "Sin datos bajistas"; },
        color: function (c) { return c.sortino ? sentiment(c.sortino.sortino_ratio) : "na"; },
      },
      {
        label: "Max Drawdown",
        value: function (c) { return c.returns ? fmtSign(c.returns.min) : "N/A"; },
        detail: function () { return "peor retorno diario"; },
        color: function (c) { return c.returns ? "negative" : "na"; },
      },
      {
        label: "RSI",
        value: function (c) { return c.rsi ? fmt(c.rsi.latest, 1) : "N/A"; },
        detail: function (c) {
          if (!c.rsi) return "";
          var v = c.rsi.latest;
          return v > 70 ? "Sobrecomprado" : v < 30 ? "Sobrevendido" : "Neutral";
        },
        color: function (c) {
          if (!c.rsi) return "na";
          var v = c.rsi.latest;
          return v > 70 ? "negative" : v < 30 ? "positive" : "neutral";
        },
      },
      {
        label: "MACD Histograma",
        value: function (c) { return c.macd ? fmt(c.macd.histogram, 3) : "N/A"; },
        detail: function (c) { return c.macd ? (c.macd.histogram >= 0 ? "Momentum alcista" : "Momentum bajista") : ""; },
        color: function (c) { return c.macd ? sentiment(c.macd.histogram) : "na"; },
      },
    ];

    return defs.map(function (def) {
      var div = document.createElement("div");
      div.className = "metric-card";
      var val    = def.value(computed);
      var detail = def.detail(computed);
      var clr    = def.color(computed);
      var arrow  = clr === "positive" ? "&#x25B2;" : clr === "negative" ? "&#x25BC;" : "";
      div.innerHTML =
        '<div class="mc-label">' + escHtml(def.label) + "</div>" +
        '<div class="mc-value ' + clr + '">' +
          (arrow ? '<span class="mc-arrow">' + arrow + "</span> " : "") +
          escHtml(val) +
        "</div>" +
        (detail ? '<div class="mc-detail">' + escHtml(detail) + "</div>" : "");
      return div;
    });
  }

  /* ─── Agent / News ─── */
  function renderAgentResults() {
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
    $.summaryBody.innerHTML = '<div class="summary-text">' + escHtml(state.agentResult.summary) + "</div>";
    $.summaryStatus.textContent = "";
    show($.newsSummarySection);
    hide($.newsPanelEmpty);
    if (state.agentResult.headlines && state.agentResult.headlines.length > 0) {
      $.headlinesList.innerHTML = state.agentResult.headlines.map(function (h) {
        return '<li class="headline-item">' + escHtml(h) + "</li>";
      }).join("");
      show($.headlinesSection);
    }
  }

  /* ─── Metrics Panel ─── */
  function loadMetricsPanel() {
    var data = state.analysisResult.data;
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
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Error " + r.status); });
        return r.json();
      })
      .then(function (data) {
        state.timeseriesResult = data;
        hide($.metricsPanelLoading);
        renderMetricsPanel();
      })
      .catch(function (err) {
        hide($.metricsPanelLoading);
        $.metricsPanelErrorMsg.textContent = "No se pudo cargar la serie de tiempo: " + err.message;
        show($.metricsPanelError);
      });
  }

  function renderMetricsPanel() {
    var computed = state.analysisResult.data.computed || {};
    var series   = (state.timeseriesResult && state.timeseriesResult.series) || {};

    show($.metricsPanelContent);

    F.renderPriceChart(series.ohlc || [], series.bollinger || [], series.prices || []);
    F.renderVolChart(series.rolling_volatility || [], computed);
    renderReturnsStats(computed);
    renderRatios(computed);
    F.renderBollingerChart(series.bollinger || [], computed);
    F.renderVolumeChart(series.volume || []);
  }

  /* ─── Returns stats table ─── */
  function renderReturnsStats(computed) {
    var r = computed.returns;
    if (!r) { $.returnsStatsGrid.innerHTML = '<p class="mc-detail">No disponible</p>'; return; }

    var rows = [
      { label: "Media diaria",   value: fmtSign(r.mean, 3),             cls: sentiment(r.mean) },
      { label: "Desv. estándar", value: fmtPct(r.std),                  cls: "neutral" },
      { label: "Mínimo",         value: fmtSign(r.min),                 cls: "negative" },
      { label: "Máximo",         value: fmtSign(r.max),                 cls: "positive" },
      { label: "Observaciones",  value: fmt(r.observations, 0) + " días", cls: "neutral" },
      { label: "Método",         value: r.method || "log",              cls: "neutral" },
    ];

    $.returnsStatsGrid.innerHTML = rows.map(function (row) {
      return '<div class="return-stat-row">' +
        '<div class="return-stat-label">' + escHtml(row.label) + '</div>' +
        '<div class="return-stat-value ' + row.cls + '">' + escHtml(row.value) + '</div>' +
        '</div>';
    }).join("");
  }

  /* ─── Ratios table ─── */
  function renderRatios(computed) {
    var rows = [
      {
        label: "Sharpe",
        value: computed.sharpe ? fmt(computed.sharpe.sharpe_ratio) : "N/A",
        detail: computed.sharpe ? "rf " + fmtPct(computed.sharpe.risk_free_rate) : "",
        cls: computed.sharpe ? sentiment(computed.sharpe.sharpe_ratio) : "na",
      },
      {
        label: "Sortino",
        value: computed.sortino ? fmt(computed.sortino.sortino_ratio) : "N/A",
        detail: computed.sortino ? computed.sortino.downside_observations + " obs bajistas" : "Sin datos bajistas",
        cls: computed.sortino ? sentiment(computed.sortino.sortino_ratio) : "na",
      },
      {
        label: "Beta",
        value: computed.beta ? fmt(computed.beta.beta) : "N/A",
        detail: computed.beta ? "vs " + computed.beta.benchmark + " · R²=" + fmt(computed.beta.r_squared) : "",
        cls: "neutral",
      },
      {
        label: "Correlación",
        value: computed.beta ? fmt(computed.beta.correlation) : "N/A",
        detail: computed.beta ? "con " + computed.beta.benchmark : "",
        cls: "neutral",
      },
      {
        label: "Volatilidad anual",
        value: computed.volatility ? fmtPct(computed.volatility["volatility(s.d.)"]) : "N/A",
        detail: computed.volatility ? fmt(computed.volatility.observations, 0) + " obs" : "",
        cls: "neutral",
      },
    ];

    $.ratiosGrid.innerHTML = rows.map(function (row) {
      return '<div class="ratio-row">' +
        '<div>' +
          '<div class="ratio-label">' + escHtml(row.label) + '</div>' +
          (row.detail ? '<div class="ratio-detail">' + escHtml(row.detail) + '</div>' : '') +
        '</div>' +
        '<div class="ratio-value ' + row.cls + '">' + escHtml(row.value) + '</div>' +
        '</div>';
    }).join("");
  }

  /* ─── Technicals Panel ─── */
  function loadTechnicalsPanel() {
    var data = state.analysisResult.data;
    $.techPanelTicker.textContent = data.ticker;
    $.techPanelMeta.textContent   = data.period.toUpperCase() + " · Indicadores técnicos";

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
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Error " + r.status); });
        return r.json();
      })
      .then(function (data) {
        state.techSeriesResult = data;
        hide($.techPanelLoading);
        renderTechnicalsPanel();
      })
      .catch(function (err) {
        hide($.techPanelLoading);
        $.techPanelErrorMsg.textContent = "No se pudo cargar indicadores: " + err.message;
        show($.techPanelError);
      });
  }

  function renderTechnicalsPanel() {
    var series = (state.techSeriesResult && state.techSeriesResult.series) || {};
    var computed = (state.analysisResult && state.analysisResult.data.computed) || {};
    show($.techPanelContent);
    F.renderRsiChart(series.rsi || [], computed);
    F.renderMacdChart(series.macd || []);
    F.renderTechBollingerChart(series.bollinger || [], computed);
  }

  /* ─── Expose ─── */
  F.renderOverview = renderOverview;
  F.renderAgentResults = renderAgentResults;
  F.loadMetricsPanel = loadMetricsPanel;
  F.loadTechnicalsPanel = loadTechnicalsPanel;

  /* ─── Event Handlers ─── */
  $.railLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      if (link.disabled) return;
      F.switchToPanel(link.dataset.panel);
    });
  });

  $.analyzeBtn.addEventListener("click", F.runAnalysis);

  $.ticker.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); F.runAnalysis(); }
  });

  $.ticker.addEventListener("input", F.validateTicker);

  $.period.addEventListener("change", function () { state.period = $.period.value; });

  $.paramsToggle.addEventListener("click", function () {
    var expanded = $.paramsToggle.getAttribute("aria-expanded") === "true";
    $.paramsToggle.setAttribute("aria-expanded", String(!expanded));
    $.paramsBody.classList.toggle("collapsed", expanded);
  });

  $.errorRetry.addEventListener("click", F.runAnalysis);

  /* Price chart toggle (candle / line) */
  document.querySelectorAll("#price-chart-toggle .toggle-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mode = btn.dataset.mode;
      if (mode === F.getPriceChartMode()) return;
      F.setPriceChartMode(mode);
      document.querySelectorAll("#price-chart-toggle .toggle-btn").forEach(function (b) {
        b.classList.toggle("toggle-btn--active", b.dataset.mode === mode);
      });
      var series = (state.timeseriesResult && state.timeseriesResult.series) || {};
      if (series.ohlc || series.bollinger || series.prices) {
        F.renderPriceChart(series.ohlc || [], series.bollinger || [], series.prices || []);
      }
    });
  });

  /* Empty state chip clicks */
  document.querySelectorAll(".empty-chip[data-ticker]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $.ticker.value = chip.dataset.ticker;
      F.runAnalysis();
    });
  });

  /* Double-click on any chart canvas resets zoom */
  document.querySelectorAll("canvas[id^='chart-']").forEach(function (canvas) {
    canvas.addEventListener("dblclick", function () {
      var chartInstance = Chart.getChart(canvas);
      if (!chartInstance) return;
      if (chartInstance.scales.y) {
        delete chartInstance.scales.y.options.min;
        delete chartInstance.scales.y.options.max;
      }
      if (chartInstance.resetZoom) chartInstance.resetZoom();
    });
  });

  /* ─── Init ─── */
  $.ticker.focus();
  F.checkHealth();
  setInterval(F.checkHealth, 30000);
})();
