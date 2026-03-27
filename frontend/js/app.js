/* ============================================================
   FINA Workspace — State, API, Rendering
   ============================================================ */

(function () {
  "use strict";

  /* ─── Constants ─── */
  var ALL_METRICS = [
    "returns", "volatility", "rolling_volatility", "sharpe",
    "sortino", "rsi", "macd", "bollinger", "beta"
  ];

  var CHART_COLORS = {
    line:     "#2b3437",
    positive: "#006d4a",
    negative: "#ba1b24",
    neutral:  "#737c7f",
    grid:     "rgba(171,179,183,0.15)",
    upper:    "rgba(186,27,36,0.15)",
    lower:    "rgba(0,109,74,0.15)",
    mid:      "#abb3b7",
  };

  /* ─── Application State ─── */
  var state = {
    ticker: "",
    period: "1y",
    metrics: ALL_METRICS.slice(),
    activePanel: "overview",
    analysisResult: null,
    timeseriesResult: null,
    agentResult: null,
    agentTicker: null,
    loading: { analysis: false, agent: false, timeseries: false },
    errors: [],
  };

  /* Chart instances — destroyed before re-creating */
  var charts = { vol: null, bb: null };

  /* ─── DOM refs ─── */
  var $ticker       = document.getElementById("ticker-input");
  var $period       = document.getElementById("period-select");
  var $analyzeBtn   = document.getElementById("analyze-btn");
  var $healthDot    = document.getElementById("health-dot");
  var $healthLbl    = document.getElementById("health-label");
  var $paramsToggle = document.getElementById("params-toggle");
  var $paramsBody   = document.getElementById("params-body");

  /* Overview panel */
  var $emptyState       = document.getElementById("empty-state");
  var $loadingState     = document.getElementById("loading-state");
  var $errorState       = document.getElementById("error-state");
  var $errorMessage     = document.getElementById("error-message");
  var $errorRetry       = document.getElementById("error-retry");
  var $resultsState     = document.getElementById("results-state");
  var $resultsTicker    = document.getElementById("results-ticker");
  var $resultsPeriod    = document.getElementById("results-period");
  var $resultsTime      = document.getElementById("results-time");
  var $metricsGrid      = document.getElementById("metrics-grid");
  var $warnings         = document.getElementById("warnings");
  var $warningsInner    = document.getElementById("warnings-inner");
  var $summaryStatus    = document.getElementById("summary-status");
  var $summaryBody      = document.getElementById("summary-body");
  var $summarySection   = document.getElementById("summary-section");
  var $headlinesSection = document.getElementById("headlines-section");
  var $headlinesList    = document.getElementById("headlines-list");

  /* Metrics panel */
  var $metricsPanel        = document.getElementById("metrics-panel");
  var $metricsPanelTicker  = document.getElementById("metrics-panel-ticker");
  var $metricsPanelMeta    = document.getElementById("metrics-panel-meta");
  var $metricsPanelLoading = document.getElementById("metrics-panel-loading");
  var $metricsPanelError   = document.getElementById("metrics-panel-error");
  var $metricsPanelErrorMsg= document.getElementById("metrics-panel-error-msg");
  var $metricsPanelContent = document.getElementById("metrics-panel-content");
  var $volStats            = document.getElementById("vol-stats");
  var $bbStats             = document.getElementById("bb-stats");
  var $returnsStatsGrid    = document.getElementById("returns-stats-grid");
  var $ratiosGrid          = document.getElementById("ratios-grid");

  /* Rail links */
  var $railLinks = document.querySelectorAll(".rail-link[data-panel]");

  /* ─── Helpers ─── */
  var TICKER_RE = /^[A-Z0-9\-=.]{1,20}$/;

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function fmt(value, decimals) {
    if (value === null || value === undefined || isNaN(value)) return "N/A";
    return Number(value).toFixed(decimals === undefined ? 2 : decimals);
  }

  function fmtPct(value, decimals) {
    if (value === null || value === undefined || isNaN(value)) return "N/A";
    return (Number(value) * 100).toFixed(decimals === undefined ? 1 : decimals) + "%";
  }

  function fmtSign(value, decimals) {
    if (value === null || value === undefined || isNaN(value)) return "N/A";
    var n = Number(value) * 100;
    var prefix = n >= 0 ? "+" : "";
    return prefix + n.toFixed(decimals === undefined ? 1 : decimals) + "%";
  }

  function sentiment(value) {
    if (value === null || value === undefined || isNaN(value)) return "na";
    return Number(value) >= 0 ? "positive" : "negative";
  }

  function escHtml(str) {
    var div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  }

  /* ─── Ticker validation ─── */
  function validateTicker() {
    var raw = $ticker.value.trim().toUpperCase();
    $ticker.value = raw;
    var valid = raw.length > 0 && TICKER_RE.test(raw);
    $ticker.classList.toggle("invalid", raw.length > 0 && !valid);
    return valid ? raw : null;
  }

  /* ─── Health check ─── */
  function checkHealth() {
    fetch("/health")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        $healthDot.className = "health-dot online";
        $healthLbl.textContent = "v" + data.version;
      })
      .catch(function () {
        $healthDot.className = "health-dot offline";
        $healthLbl.textContent = "offline";
      });
  }

  /* ─── Read selected metrics ─── */
  function readSelectedMetrics() {
    var checks = $paramsBody.querySelectorAll('input[type="checkbox"]');
    var selected = [];
    checks.forEach(function (cb) { if (cb.checked) selected.push(cb.value); });
    return selected;
  }

  /* ─── Panel Navigation ─── */
  function setActiveRailLink(panelName) {
    $railLinks.forEach(function (link) {
      var isActive = link.dataset.panel === panelName;
      link.classList.toggle("rail-link--active", isActive);
      if (isActive) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function switchToPanel(panelName) {
    /* Hide overview canvas states */
    hide($emptyState);
    hide($loadingState);
    hide($errorState);
    hide($resultsState);
    /* Hide metrics panel */
    hide($metricsPanel);

    state.activePanel = panelName;
    setActiveRailLink(panelName);

    if (panelName === "overview") {
      if (!state.analysisResult) {
        show($emptyState);
      } else {
        show($resultsState);
      }
    } else if (panelName === "metrics") {
      show($metricsPanel);
      if (state.analysisResult) {
        loadMetricsPanel();
      } else {
        /* Show empty prompt inside metrics panel */
        hide($metricsPanelLoading);
        hide($metricsPanelContent);
        hide($metricsPanelError);
        $metricsPanelTicker.textContent = "";
        $metricsPanelMeta.textContent = "Ingresa un ticker y presiona Analizar";
      }
    }
  }

  /* ─── Run analysis ─── */
  function runAnalysis() {
    var ticker = validateTicker();
    if (!ticker) { $ticker.focus(); return; }

    var tickerChanged = ticker !== state.agentTicker;

    state.ticker  = ticker;
    state.period  = $period.value;
    state.metrics = readSelectedMetrics();
    state.errors  = [];
    state.analysisResult    = null;
    state.timeseriesResult  = null;
    if (tickerChanged) state.agentResult = null;
    if (state.metrics.length === 0) state.metrics = ALL_METRICS.slice();

    /* Reset to overview loading */
    state.activePanel = "overview";
    setActiveRailLink("overview");
    hide($emptyState);
    hide($errorState);
    hide($resultsState);
    hide($metricsPanel);
    show($loadingState);

    $analyzeBtn.disabled = true;
    state.loading.analysis = true;

    /* Analysis request */
    var analysisPromise = fetch("/analysis/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: state.ticker, period: state.period, metrics: state.metrics }),
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Error " + r.status); });
        return r.json();
      })
      .then(function (data) { state.analysisResult = data; state.loading.analysis = false; })
      .catch(function (err) { state.loading.analysis = false; state.errors.push(err.message); });

    /* Agent — only when ticker changes */
    var agentPromise;
    if (tickerChanged) {
      state.loading.agent = true;
      agentPromise = fetch("/agent/summarize/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: state.ticker }),
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Agent error " + r.status); });
          return r.json();
        })
        .then(function (data) { state.agentResult = data; state.agentTicker = state.ticker; state.loading.agent = false; })
        .catch(function () { state.loading.agent = false; });
    } else {
      agentPromise = Promise.resolve();
    }

    analysisPromise.then(function () {
      $analyzeBtn.disabled = false;

      if (state.errors.length > 0 && !state.analysisResult) {
        $errorMessage.textContent = state.errors.join("\n");
        hide($loadingState);
        show($errorState);
        return;
      }

      if (state.analysisResult) {
        renderOverview();
        hide($loadingState);
        show($resultsState);
      }

      agentPromise.then(renderAgentResults);
    });
  }

  /* ─── Overview rendering ─── */
  function renderOverview() {
    var data = state.analysisResult.data;
    var computed = data.computed || {};
    var warnings = computed.warnings || [];

    $resultsTicker.textContent = data.ticker;
    $resultsPeriod.textContent = data.period.toUpperCase();
    $resultsTime.textContent   = new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });

    var cards = buildMetricCards(computed);
    $metricsGrid.innerHTML = "";
    cards.forEach(function (card) { $metricsGrid.appendChild(card); });

    if (warnings.length > 0) {
      $warningsInner.innerHTML = warnings.map(function (w) {
        return '<div class="warning-item"><span class="warning-icon">!</span><span>' + escHtml(w) + "</span></div>";
      }).join("");
      show($warnings);
    } else {
      hide($warnings);
    }

    show($summarySection);
    $summaryBody.innerHTML = '<div class="summary-loading"><span class="spinner"></span><span>Generando resumen...</span></div>';
    $summaryStatus.textContent = "";
    hide($headlinesSection);
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
      div.innerHTML =
        '<div class="mc-value ' + def.color(computed) + '">' + escHtml(val) + "</div>" +
        '<div class="mc-label">' + escHtml(def.label) + "</div>" +
        (detail ? '<div class="mc-detail">' + escHtml(detail) + "</div>" : "");
      return div;
    });
  }

  function renderAgentResults() {
    if (!state.agentResult) {
      $summaryBody.innerHTML = '<div class="summary-error">Resumen IA no disponible.</div>';
      $summaryStatus.textContent = "error";
      return;
    }
    $summaryBody.innerHTML = '<div class="summary-text">' + escHtml(state.agentResult.summary) + "</div>";
    $summaryStatus.textContent = "";
    if (state.agentResult.headlines && state.agentResult.headlines.length > 0) {
      $headlinesList.innerHTML = state.agentResult.headlines.map(function (h) {
        return '<li class="headline-item">' + escHtml(h) + "</li>";
      }).join("");
      show($headlinesSection);
    }
  }

  /* ─── Metrics Panel ─── */
  function loadMetricsPanel() {
    var data = state.analysisResult.data;
    $metricsPanelTicker.textContent = data.ticker;
    $metricsPanelMeta.textContent   = data.period.toUpperCase();

    /* If timeseries already loaded for this ticker+period, just render */
    if (state.timeseriesResult &&
        state.timeseriesResult.ticker === state.ticker &&
        state.timeseriesResult.period === state.period) {
      renderMetricsPanel();
      return;
    }

    /* Show loading */
    hide($metricsPanelContent);
    hide($metricsPanelError);
    show($metricsPanelLoading);

    fetch("/analysis/timeseries/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: state.ticker,
        period: state.period,
        series: ["rolling_volatility", "bollinger"],
      }),
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Error " + r.status); });
        return r.json();
      })
      .then(function (data) {
        state.timeseriesResult = data;
        hide($metricsPanelLoading);
        renderMetricsPanel();
      })
      .catch(function (err) {
        hide($metricsPanelLoading);
        $metricsPanelErrorMsg.textContent = "No se pudo cargar la serie de tiempo: " + err.message;
        show($metricsPanelError);
      });
  }

  function renderMetricsPanel() {
    var computed = state.analysisResult.data.computed || {};
    var series   = (state.timeseriesResult && state.timeseriesResult.series) || {};

    show($metricsPanelContent);

    renderVolChart(series.rolling_volatility || [], computed);
    renderReturnsStats(computed);
    renderRatios(computed);
    renderBollingerChart(series.bollinger || [], computed);
  }

  /* Chart.js shared config */
  function baseChartOptions(yTickFmt) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#2b3437",
          titleColor: "#abb3b7",
          bodyColor: "#f8f9fa",
          borderColor: "rgba(171,179,183,0.2)",
          borderWidth: 1,
          padding: 10,
          cornerRadius: 6,
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#737c7f",
            font: { family: "Inter", size: 10 },
            maxTicksLimit: 8,
            maxRotation: 0,
          },
          grid: { color: CHART_COLORS.grid },
        },
        y: {
          ticks: {
            color: "#737c7f",
            font: { family: "Inter", size: 10 },
            callback: yTickFmt || function (v) { return v; },
          },
          grid: { color: CHART_COLORS.grid },
        },
      },
    };
  }

  function sparseLabels(arr, max) {
    if (arr.length <= max) return arr;
    var step = Math.floor(arr.length / max);
    return arr.map(function (v, i) { return i % step === 0 ? v : ""; });
  }

  /* Rolling Volatility chart */
  function renderVolChart(volSeries, computed) {
    destroyChart("vol");
    if (!volSeries.length) return;

    var labels = volSeries.map(function (d) { return d.date; });
    var values = volSeries.map(function (d) { return d.value !== null ? +(d.value * 100).toFixed(2) : null; });

    var latest = computed.rolling_volatility;
    var latestVal = latest ? (latest.latest_sd * 100).toFixed(1) + "%" : "N/A";

    $volStats.innerHTML =
      '<div class="chart-stat">' +
      '<span class="chart-stat-value">' + escHtml(latestVal) + '</span>' +
      '<span class="chart-stat-label">Actual</span>' +
      '</div>';

    var opts = baseChartOptions(function (v) { return v + "%"; });
    opts.scales.y.min = 0;

    charts.vol = new Chart(document.getElementById("chart-vol"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [{
          data: values,
          borderColor: CHART_COLORS.line,
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: true,
          backgroundColor: "rgba(43,52,55,0.04)",
        }],
      },
      options: opts,
    });
  }

  /* Returns stats table */
  function renderReturnsStats(computed) {
    var r = computed.returns;
    if (!r) { $returnsStatsGrid.innerHTML = '<p class="mc-detail">No disponible</p>'; return; }

    var rows = [
      { label: "Media diaria",   value: fmtSign(r.mean, 3),             cls: sentiment(r.mean) },
      { label: "Desv. estándar", value: fmtPct(r.std),                  cls: "neutral" },
      { label: "Mínimo",         value: fmtSign(r.min),                 cls: "negative" },
      { label: "Máximo",         value: fmtSign(r.max),                 cls: "positive" },
      { label: "Observaciones",  value: fmt(r.observations, 0) + " días", cls: "neutral" },
      { label: "Método",         value: r.method || "log",              cls: "neutral" },
    ];

    $returnsStatsGrid.innerHTML = rows.map(function (row) {
      return '<div class="return-stat-row">' +
        '<div class="return-stat-label">' + escHtml(row.label) + '</div>' +
        '<div class="return-stat-value ' + row.cls + '">' + escHtml(row.value) + '</div>' +
        '</div>';
    }).join("");
  }

  /* Ratios table */
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

    $ratiosGrid.innerHTML = rows.map(function (row) {
      return '<div class="ratio-row">' +
        '<div>' +
          '<div class="ratio-label">' + escHtml(row.label) + '</div>' +
          (row.detail ? '<div class="ratio-detail">' + escHtml(row.detail) + '</div>' : '') +
        '</div>' +
        '<div class="ratio-value ' + row.cls + '">' + escHtml(row.value) + '</div>' +
        '</div>';
    }).join("");
  }

  /* Bollinger Bands chart */
  function renderBollingerChart(bbSeries, computed) {
    destroyChart("bb");
    if (!bbSeries.length) return;

    var labels = bbSeries.map(function (d) { return d.date; });
    var price  = bbSeries.map(function (d) { return d.price !== null ? +d.price.toFixed(2) : null; });
    var upper  = bbSeries.map(function (d) { return d.upper !== null ? +d.upper.toFixed(2) : null; });
    var mid    = bbSeries.map(function (d) { return d.middle !== null ? +d.middle.toFixed(2) : null; });
    var lower  = bbSeries.map(function (d) { return d.lower !== null ? +d.lower.toFixed(2) : null; });

    var bb = computed.bollinger;
    if (bb) {
      $bbStats.innerHTML =
        '<div class="chart-stat"><span class="chart-stat-value negative">' + escHtml(fmt(bb.upper, 2)) + '</span><span class="chart-stat-label">Superior</span></div>' +
        '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(bb.middle, 2)) + '</span><span class="chart-stat-label">Media</span></div>' +
        '<div class="chart-stat"><span class="chart-stat-value positive">' + escHtml(fmt(bb.lower, 2)) + '</span><span class="chart-stat-label">Inferior</span></div>' +
        '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(bb.percent_b, 2)) + '</span><span class="chart-stat-label">%B</span></div>';
    }

    var opts = baseChartOptions(function (v) { return "$" + v; });
    opts.plugins.tooltip.callbacks = {
      label: function (ctx) {
        return ctx.dataset.label + ": $" + ctx.parsed.y.toFixed(2);
      },
    };

    charts.bb = new Chart(document.getElementById("chart-bb"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          {
            label: "Superior",
            data: upper,
            borderColor: "rgba(186,27,36,0.5)",
            borderWidth: 1,
            borderDash: [4, 3],
            pointRadius: 0,
            fill: false,
          },
          {
            label: "Media",
            data: mid,
            borderColor: CHART_COLORS.mid,
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
          },
          {
            label: "Inferior",
            data: lower,
            borderColor: "rgba(0,109,74,0.5)",
            borderWidth: 1,
            borderDash: [4, 3],
            pointRadius: 0,
            fill: false,
          },
          {
            label: "Precio",
            data: price,
            borderColor: CHART_COLORS.line,
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.2,
            fill: false,
          },
        ],
      },
      options: opts,
    });
  }

  /* ─── Rail Navigation Events ─── */
  $railLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      if (link.disabled) return;
      switchToPanel(link.dataset.panel);
    });
  });

  /* ─── Analyze button & Enter ─── */
  $analyzeBtn.addEventListener("click", runAnalysis);

  $ticker.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); runAnalysis(); }
  });

  $ticker.addEventListener("input", validateTicker);

  $period.addEventListener("change", function () { state.period = $period.value; });

  $paramsToggle.addEventListener("click", function () {
    var expanded = $paramsToggle.getAttribute("aria-expanded") === "true";
    $paramsToggle.setAttribute("aria-expanded", String(!expanded));
    $paramsBody.classList.toggle("collapsed", expanded);
  });

  $errorRetry.addEventListener("click", runAnalysis);

  /* ─── Init ─── */
  $ticker.focus();
  checkHealth();
  setInterval(checkHealth, 30000);

})();
