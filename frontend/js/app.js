/* ============================================================
   FINA Workspace — State, API, Rendering
   ============================================================ */

(function () {
  "use strict";

  /* ─── Register zoom plugin ─── */
  if (window.ChartZoom) Chart.register(window.ChartZoom);

  /* ─── Candlestick wick plugin (draws high/low lines on floating bars) ─── */
  var candleWickPlugin = {
    id: "candleWick",
    afterDatasetsDraw: function (chart) {
      var meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !chart.data.datasets[0]._ohlc) return;
      var ctx = chart.ctx;
      var ohlc = chart.data.datasets[0]._ohlc;
      ctx.save();
      ctx.lineWidth = 1.2;
      meta.data.forEach(function (bar, i) {
        if (!ohlc[i]) return;
        var high = chart.scales.y.getPixelForValue(ohlc[i].high);
        var low  = chart.scales.y.getPixelForValue(ohlc[i].low);
        var x    = bar.x;
        ctx.strokeStyle = ohlc[i].close >= ohlc[i].open ? CHART_COLORS.wickUp : CHART_COLORS.wickDn;
        ctx.beginPath();
        ctx.moveTo(x, high);
        ctx.lineTo(x, low);
        ctx.stroke();
      });
      ctx.restore();
    },
  };
  Chart.register(candleWickPlugin);

  /* ─── Constants ─── */
  var ALL_METRICS = [
    "returns", "volatility", "rolling_volatility", "sharpe",
    "sortino", "rsi", "macd", "bollinger", "beta"
  ];

  var CHART_COLORS = {
    line:     "#1a56db",           /* indigo — primary data, high contrast on white */
    positive: "#006d4a",
    negative: "#ba1b24",
    neutral:  "#586064",
    grid:     "rgba(171,179,183,0.18)",
    upper:    "rgba(186,27,36,0.25)",
    lower:    "rgba(0,109,74,0.25)",
    mid:      "#8b5cf6",           /* violet — SMA/media, distinct from price line */
    band:     "rgba(139,92,246,0.08)", /* violet fill between bands */
    fill:     "rgba(26,86,219,0.10)",  /* indigo fill under vol line */
    volume:   "rgba(107,114,128,0.35)",/* gray bars for volume */
    volumeAvg:"#f59e0b",              /* amber line for avg volume */
    candleUp:  "#006d4a",             /* green body — close > open */
    candleDn:  "#ba1b24",             /* red body — close < open */
    wickUp:    "#006d4a",
    wickDn:    "#ba1b24",
  };

  /* ─── Application State ─── */
  var state = {
    ticker: "",
    period: "1y",
    metrics: ALL_METRICS.slice(),
    activePanel: "overview",
    analysisResult: null,
    timeseriesResult: null,
    techSeriesResult: null,
    agentResult: null,
    agentTicker: null,
    loading: { analysis: false, agent: false, timeseries: false },
    errors: [],
  };

  /* Chart instances — destroyed before re-creating */
  var charts = { vol: null, bb: null, volume: null, rsi: null, macd: null, techBb: null, price: null };
  var priceChartMode = "candle"; /* "candle" or "line" */

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
  var $volumeStats         = document.getElementById("volume-stats");
  var $priceStats          = document.getElementById("price-stats");
  var $priceChartSubtitle  = document.getElementById("price-chart-subtitle");
  var $returnsStatsGrid    = document.getElementById("returns-stats-grid");
  var $ratiosGrid          = document.getElementById("ratios-grid");

  /* News & IA panel */
  var $newsPanel           = document.getElementById("news-panel");
  var $newsPanelTicker     = document.getElementById("news-panel-ticker");
  var $newsPanelMeta       = document.getElementById("news-panel-meta");
  var $newsPanelEmpty      = document.getElementById("news-panel-empty");
  var $newsSummarySection  = document.getElementById("news-summary-section");

  /* Technicals panel */
  var $techPanel           = document.getElementById("technicals-panel");
  var $techPanelTicker     = document.getElementById("tech-panel-ticker");
  var $techPanelMeta       = document.getElementById("tech-panel-meta");
  var $techPanelLoading    = document.getElementById("tech-panel-loading");
  var $techPanelError      = document.getElementById("tech-panel-error");
  var $techPanelErrorMsg   = document.getElementById("tech-panel-error-msg");
  var $techPanelContent    = document.getElementById("tech-panel-content");
  var $rsiStats            = document.getElementById("rsi-stats");
  var $macdStats           = document.getElementById("macd-stats");
  var $techBbStats         = document.getElementById("tech-bb-stats");

  /* Methodology panel */
  var $methodologyPanel    = document.getElementById("methodology-panel");

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
    /* Hide all panels */
    hide($emptyState);
    hide($loadingState);
    hide($errorState);
    hide($resultsState);
    hide($metricsPanel);
    hide($techPanel);
    hide($newsPanel);
    hide($methodologyPanel);

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
        hide($metricsPanelLoading);
        hide($metricsPanelContent);
        hide($metricsPanelError);
        $metricsPanelTicker.textContent = "";
        $metricsPanelMeta.textContent = "Ingresa un ticker y presiona Analizar";
      }
    } else if (panelName === "news") {
      show($newsPanel);
      if (state.agentResult) {
        $newsPanelTicker.textContent = state.agentTicker || "";
        $newsPanelMeta.textContent = "Noticias & Análisis IA";
        hide($newsPanelEmpty);
        show($newsSummarySection);
        renderAgentResults();
      } else if (state.loading.agent) {
        $newsPanelTicker.textContent = state.ticker || "";
        $newsPanelMeta.textContent = "Cargando...";
        hide($newsPanelEmpty);
        show($newsSummarySection);
      } else {
        $newsPanelTicker.textContent = "";
        $newsPanelMeta.textContent = "Noticias & Análisis IA";
        hide($newsSummarySection);
        hide($headlinesSection);
        show($newsPanelEmpty);
      }
    } else if (panelName === "technicals") {
      show($techPanel);
      if (state.analysisResult) {
        loadTechnicalsPanel();
      } else {
        hide($techPanelLoading);
        hide($techPanelContent);
        hide($techPanelError);
        $techPanelTicker.textContent = "";
        $techPanelMeta.textContent = "Ingresa un ticker y presiona Analizar";
      }
    } else if (panelName === "methodology") {
      show($methodologyPanel);
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
    state.techSeriesResult  = null;
    if (tickerChanged) state.agentResult = null;
    if (state.metrics.length === 0) state.metrics = ALL_METRICS.slice();

    /* Reset to overview loading */
    state.activePanel = "overview";
    setActiveRailLink("overview");
    hide($emptyState);
    hide($errorState);
    hide($resultsState);
    hide($metricsPanel);
    hide($techPanel);
    hide($newsPanel);
    hide($methodologyPanel);
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
        state.processTimeMs = r.headers.get("X-Process-Time-Ms");
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
    var timeParts = [new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })];
    if (state.processTimeMs) timeParts.push(parseFloat(state.processTimeMs).toFixed(0) + "ms");
    var obs = computed.returns ? computed.returns.observations : null;
    if (obs) timeParts.push(fmt(obs, 0) + " obs");
    $resultsTime.textContent = timeParts.join(" · ");
    document.title = "FINA — " + data.ticker;

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

  function renderAgentResults() {
    /* Update news panel header */
    if (state.agentTicker) {
      $newsPanelTicker.textContent = state.agentTicker;
      $newsPanelMeta.textContent = "Noticias & Análisis IA";
    }

    if (!state.agentResult) {
      $summaryBody.innerHTML = '<div class="summary-error">Resumen IA no disponible.</div>';
      $summaryStatus.textContent = "error";
      show($newsSummarySection);
      hide($newsPanelEmpty);
      return;
    }
    $summaryBody.innerHTML = '<div class="summary-text">' + escHtml(state.agentResult.summary) + "</div>";
    $summaryStatus.textContent = "";
    show($newsSummarySection);
    hide($newsPanelEmpty);
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
        series: ["prices", "rolling_volatility", "bollinger", "volume", "ohlc"],
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

    renderPriceChart(series.ohlc || [], series.bollinger || [], series.prices || []);
    renderVolChart(series.rolling_volatility || [], computed);
    renderReturnsStats(computed);
    renderRatios(computed);
    renderBollingerChart(series.bollinger || [], computed);
    renderVolumeChart(series.volume || []);
  }

  /* Chart.js shared config.
     fullDates: the complete array of date strings — used so tooltips
     always show the real date even when the x-axis labels are sparse. */
  /**
   * Auto-scale Y axis to fit visible data after zoom/pan on X axis.
   * Scans all datasets for values within the current X viewport,
   * then sets y.min / y.max with a 5% padding.
   */
  function autoScaleY(chart) {
    var xScale = chart.scales.x;
    var yScale = chart.scales.y;
    if (!xScale || !yScale) return;

    var minIdx = Math.max(0, Math.floor(xScale.min));
    var maxIdx = Math.min(xScale.max, chart.data.labels.length - 1);
    if (maxIdx <= minIdx) return;

    var yMin = Infinity;
    var yMax = -Infinity;

    chart.data.datasets.forEach(function (ds) {
      for (var i = minIdx; i <= maxIdx; i++) {
        var val = ds.data[i];
        if (val === null || val === undefined) continue;
        /* Floating bar: val is [low, high] */
        if (Array.isArray(val)) {
          if (val[0] < yMin) yMin = val[0];
          if (val[1] > yMax) yMax = val[1];
          /* Also check OHLC wicks if available */
          if (ds._ohlc && ds._ohlc[i]) {
            if (ds._ohlc[i].low < yMin) yMin = ds._ohlc[i].low;
            if (ds._ohlc[i].high > yMax) yMax = ds._ohlc[i].high;
          }
        } else {
          if (val < yMin) yMin = val;
          if (val > yMax) yMax = val;
        }
      }
    });

    if (yMin === Infinity || yMax === -Infinity) return;

    var padding = (yMax - yMin) * 0.05 || 1;
    yScale.options.min = yMin - padding;
    yScale.options.max = yMax + padding;
    chart.update("none");
  }

  function baseChartOptions(yTickFmt, fullDates) {
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
          callbacks: {
            title: function (items) {
              if (!items.length) return "";
              var idx = items[0].dataIndex;
              return fullDates && fullDates[idx] ? fullDates[idx] : items[0].label;
            },
          },
        },
        zoom: {
          pan: {
            enabled: true,
            mode: "xy",
            onPanComplete: function (ctx) { autoScaleY(ctx.chart); },
          },
          zoom: {
            wheel: { enabled: true, speed: 0.1 },
            pinch: { enabled: true },
            mode: "xy",
            onZoomComplete: function (ctx) { autoScaleY(ctx.chart); },
          },
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

  function showChartEmpty(canvasId, msg) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext("2d");
    canvas.width = canvas.parentElement.clientWidth || 300;
    canvas.height = 80;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#737c7f";
    ctx.font = "13px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(msg || "Datos insuficientes para este período", canvas.width / 2, 45);
  }

  function sparseLabels(arr, max) {
    if (arr.length <= max) return arr;
    var step = Math.floor(arr.length / max);
    return arr.map(function (v, i) { return i % step === 0 ? v : ""; });
  }

  /* ─── Price chart (Candlestick / Line toggle) ─── */
  function renderPriceChart(ohlcSeries, bbSeries, pricesSeries) {
    destroyChart("price");
    if (!ohlcSeries.length && !bbSeries.length && !(pricesSeries && pricesSeries.length)) {
      showChartEmpty("chart-price", "Datos insuficientes para el gráfico de precios");
      $priceStats.innerHTML = "";
      return;
    }

    /* Extract close from ohlc, bollinger, or raw prices as fallback */
    var source = ohlcSeries.length ? ohlcSeries : (bbSeries.length ? bbSeries : pricesSeries);
    var labels = source.map(function (d) { return d.date; });

    /* Stats */
    var latestClose = ohlcSeries.length ? ohlcSeries[ohlcSeries.length - 1].close : (bbSeries.length ? bbSeries[bbSeries.length - 1].price : (pricesSeries && pricesSeries.length ? pricesSeries[pricesSeries.length - 1].value : null));
    var firstClose  = ohlcSeries.length ? ohlcSeries[0].close : (bbSeries.length ? bbSeries[0].price : (pricesSeries && pricesSeries.length ? pricesSeries[0].value : null));
    var changePct = (latestClose && firstClose) ? ((latestClose - firstClose) / firstClose * 100) : null;
    var changeCls = changePct !== null ? (changePct >= 0 ? "positive" : "negative") : "";

    $priceStats.innerHTML =
      '<div class="chart-stat">' +
        '<span class="chart-stat-value">$' + escHtml(latestClose !== null ? latestClose.toFixed(2) : "N/A") + '</span>' +
        '<span class="chart-stat-label">Último</span>' +
      '</div>' +
      (changePct !== null ?
        '<div class="chart-stat"><span class="chart-stat-value ' + changeCls + '">' +
          escHtml((changePct >= 0 ? "+" : "") + changePct.toFixed(2) + "%") +
        '</span><span class="chart-stat-label">Período</span></div>' : "");

    if (priceChartMode === "candle" && ohlcSeries.length) {
      renderCandlestick(ohlcSeries, labels);
    } else {
      renderPriceLine(ohlcSeries.length ? ohlcSeries : (bbSeries.length ? bbSeries : pricesSeries), labels);
    }
  }

  function renderCandlestick(ohlcSeries, labels) {
    var ohlcData = ohlcSeries.map(function (d) {
      return { open: d.open, high: d.high, low: d.low, close: d.close };
    });

    /* Floating bar: y = [min(open,close), max(open,close)] for body */
    var bodies = ohlcData.map(function (d) {
      return [Math.min(d.open, d.close), Math.max(d.open, d.close)];
    });

    var barColors = ohlcData.map(function (d) {
      return d.close >= d.open ? CHART_COLORS.candleUp : CHART_COLORS.candleDn;
    });

    var opts = baseChartOptions(function (v) { return "$" + v.toFixed(0); }, labels);
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      var i = ctx.dataIndex;
      var d = ohlcData[i];
      if (!d) return "";
      return [
        "O: $" + d.open.toFixed(2),
        "H: $" + d.high.toFixed(2),
        "L: $" + d.low.toFixed(2),
        "C: $" + d.close.toFixed(2),
      ];
    };
    opts.interaction.mode = "nearest";

    charts.price = new Chart(document.getElementById("chart-price"), {
      type: "bar",
      data: {
        labels: sparseLabels(labels, 12),
        datasets: [{
          data: bodies,
          backgroundColor: barColors,
          borderColor: barColors,
          borderWidth: 1,
          borderSkipped: false,
          barPercentage: 0.6,
          categoryPercentage: 0.9,
          _ohlc: ohlcData,
        }],
      },
      options: opts,
    });

    $priceChartSubtitle.textContent = "OHLC Candlestick";
  }

  function renderPriceLine(series, labels) {
    var prices = series.map(function (d) {
      return d.close !== undefined ? +d.close.toFixed(2) : (d.price !== undefined ? +d.price.toFixed(2) : (d.value !== undefined && d.value !== null ? +d.value.toFixed(2) : null));
    });

    var opts = baseChartOptions(function (v) { return "$" + v; }, labels);
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      return "Precio: $" + ctx.parsed.y.toFixed(2);
    };

    charts.price = new Chart(document.getElementById("chart-price"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [{
          data: prices,
          borderColor: CHART_COLORS.line,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          backgroundColor: CHART_COLORS.fill,
        }],
      },
      options: opts,
    });

    $priceChartSubtitle.textContent = "Cierre ajustado";
  }

  /* Rolling Volatility chart */
  function renderVolChart(volSeries, computed) {
    destroyChart("vol");
    if (!volSeries.length) {
      showChartEmpty("chart-vol", "Datos insuficientes para volatilidad rolling (mín. 22 obs)");
      $volStats.innerHTML = "";
      return;
    }

    var labels = volSeries.map(function (d) { return d.date; });
    var values = volSeries.map(function (d) { return d.value !== null ? +(d.value * 100).toFixed(2) : null; });

    var latest = computed.rolling_volatility;
    var latestVal = latest ? (latest.latest_sd * 100).toFixed(1) + "%" : "N/A";

    $volStats.innerHTML =
      '<div class="chart-stat">' +
      '<span class="chart-stat-value">' + escHtml(latestVal) + '</span>' +
      '<span class="chart-stat-label">Actual</span>' +
      '</div>';

    var opts = baseChartOptions(function (v) { return v + "%"; }, labels);
    opts.scales.y.min = 0;
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      return "Volatilidad: " + ctx.parsed.y.toFixed(2) + "%";
    };

    charts.vol = new Chart(document.getElementById("chart-vol"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [{
          data: values,
          borderColor: CHART_COLORS.line,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: true,
          backgroundColor: CHART_COLORS.fill,
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
    if (!bbSeries.length) {
      showChartEmpty("chart-bb", "Datos insuficientes para Bollinger Bands (mín. 20 obs)");
      return;
    }

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

    var opts = baseChartOptions(function (v) { return "$" + v; }, labels);
    opts.plugins.legend = {
      display: true,
      position: "bottom",
      labels: {
        color: "#586064",
        font: { family: "Inter", size: 11 },
        boxWidth: 12,
        boxHeight: 2,
        padding: 16,
        usePointStyle: false,
      },
    };
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      return ctx.dataset.label + ": $" + ctx.parsed.y.toFixed(2);
    };

    charts.bb = new Chart(document.getElementById("chart-bb"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          {
            label: "Superior",
            data: upper,
            borderColor: CHART_COLORS.negative,
            borderWidth: 1.2,
            borderDash: [5, 3],
            pointRadius: 0,
            fill: false,
          },
          {
            label: "Media",
            data: mid,
            borderColor: CHART_COLORS.mid,
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
          },
          {
            label: "Inferior",
            data: lower,
            borderColor: CHART_COLORS.positive,
            borderWidth: 1.2,
            borderDash: [5, 3],
            pointRadius: 0,
            fill: "-2",
            backgroundColor: CHART_COLORS.band,
          },
          {
            label: "Precio",
            data: price,
            borderColor: CHART_COLORS.line,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.2,
            fill: false,
          },
        ],
      },
      options: opts,
    });
  }

  /* ─── Technicals Panel ─── */
  function loadTechnicalsPanel() {
    var data = state.analysisResult.data;
    $techPanelTicker.textContent = data.ticker;
    $techPanelMeta.textContent   = data.period.toUpperCase() + " · Indicadores técnicos";

    if (state.techSeriesResult &&
        state.techSeriesResult.ticker === state.ticker &&
        state.techSeriesResult.period === state.period) {
      renderTechnicalsPanel();
      return;
    }

    hide($techPanelContent);
    hide($techPanelError);
    show($techPanelLoading);

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
        hide($techPanelLoading);
        renderTechnicalsPanel();
      })
      .catch(function (err) {
        hide($techPanelLoading);
        $techPanelErrorMsg.textContent = "No se pudo cargar indicadores: " + err.message;
        show($techPanelError);
      });
  }

  function renderTechnicalsPanel() {
    var series = (state.techSeriesResult && state.techSeriesResult.series) || {};
    var computed = (state.analysisResult && state.analysisResult.data.computed) || {};
    show($techPanelContent);
    renderRsiChart(series.rsi || [], computed);
    renderMacdChart(series.macd || []);
    renderTechBollingerChart(series.bollinger || [], computed);
  }

  /* RSI chart with overbought/oversold zones */
  function renderRsiChart(rsiSeries, computed) {
    destroyChart("rsi");
    if (!rsiSeries.length) {
      showChartEmpty("chart-rsi", "Datos insuficientes para RSI (mín. 15 obs)");
      $rsiStats.innerHTML = "";
      return;
    }

    var labels = rsiSeries.map(function (d) { return d.date; });
    var values = rsiSeries.map(function (d) { return d.value !== null ? +d.value.toFixed(1) : null; });

    var rsi = computed.rsi;
    var rsiVal = rsi ? rsi.latest : null;
    var latestVal = rsiVal !== null ? rsiVal.toFixed(1) : "N/A";
    var latestCls = rsiVal !== null ? (rsiVal > 70 ? "negative" : rsiVal < 30 ? "positive" : "") : "";
    var latestLbl = rsiVal !== null ? (rsiVal > 70 ? "Sobrecompra" : rsiVal < 30 ? "Sobreventa" : "Neutral") : "";

    $rsiStats.innerHTML =
      '<div class="chart-stat"><span class="chart-stat-value ' + latestCls + '">' + escHtml(latestVal) + '</span><span class="chart-stat-label">' + escHtml(latestLbl) + '</span></div>';

    var opts = baseChartOptions(function (v) { return v; }, labels);
    opts.scales.y.min = 0;
    opts.scales.y.max = 100;
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };

    /* Reference lines at 70 and 30 as constant datasets */
    var overbought = values.map(function () { return 70; });
    var oversold   = values.map(function () { return 30; });

    charts.rsi = new Chart(document.getElementById("chart-rsi"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          {
            label: "Sobrecompra (70)",
            data: overbought,
            borderColor: "rgba(186,27,36,0.35)",
            borderWidth: 1,
            borderDash: [4, 3],
            pointRadius: 0,
            fill: false,
          },
          {
            label: "Sobreventa (30)",
            data: oversold,
            borderColor: "rgba(0,109,74,0.35)",
            borderWidth: 1,
            borderDash: [4, 3],
            pointRadius: 0,
            fill: false,
          },
          {
            label: "RSI",
            data: values,
            borderColor: CHART_COLORS.line,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: false,
          },
        ],
      },
      options: opts,
    });
  }

  /* MACD chart: MACD line, signal line, histogram bars */
  function renderMacdChart(macdSeries) {
    destroyChart("macd");
    if (!macdSeries.length) {
      showChartEmpty("chart-macd", "Datos insuficientes para MACD (mín. 35 obs)");
      return;
    }

    var labels    = macdSeries.map(function (d) { return d.date; });
    var macdLine  = macdSeries.map(function (d) { return d.macd !== null ? +d.macd.toFixed(3) : null; });
    var signalLine= macdSeries.map(function (d) { return d.signal !== null ? +d.signal.toFixed(3) : null; });
    var histogram = macdSeries.map(function (d) { return d.histogram !== null ? +d.histogram.toFixed(3) : null; });

    var latestMacd = macdLine[macdLine.length - 1];
    var latestSignal = signalLine[signalLine.length - 1];
    var latestHist = histogram[histogram.length - 1];

    $macdStats.innerHTML =
      '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(latestMacd, 3)) + '</span><span class="chart-stat-label">MACD</span></div>' +
      '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(latestSignal, 3)) + '</span><span class="chart-stat-label">Signal</span></div>' +
      '<div class="chart-stat"><span class="chart-stat-value ' + (latestHist >= 0 ? "positive" : "negative") + '">' + escHtml(fmt(latestHist, 3)) + '</span><span class="chart-stat-label">Histograma</span></div>';

    var histColors = histogram.map(function (v) {
      return v >= 0 ? CHART_COLORS.positive : CHART_COLORS.negative;
    });

    var opts = baseChartOptions(function (v) { return v; }, labels);
    opts.plugins.legend = {
      display: true,
      position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };

    charts.macd = new Chart(document.getElementById("chart-macd"), {
      type: "bar",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          {
            label: "Histograma",
            data: histogram,
            backgroundColor: histColors,
            borderWidth: 0,
            borderRadius: 1,
            order: 3,
          },
          {
            label: "MACD",
            data: macdLine,
            type: "line",
            borderColor: CHART_COLORS.line,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: false,
            order: 1,
          },
          {
            label: "Signal",
            data: signalLine,
            type: "line",
            borderColor: "#f59e0b",
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.3,
            fill: false,
            order: 2,
          },
        ],
      },
      options: opts,
    });
  }

  /* Technicals Bollinger chart (same as metrics but separate canvas) */
  function renderTechBollingerChart(bbSeries, computed) {
    destroyChart("techBb");
    if (!bbSeries.length) {
      showChartEmpty("chart-tech-bb", "Datos insuficientes para Bollinger Bands (mín. 20 obs)");
      return;
    }

    var labels = bbSeries.map(function (d) { return d.date; });
    var price  = bbSeries.map(function (d) { return d.price !== null ? +d.price.toFixed(2) : null; });
    var upper  = bbSeries.map(function (d) { return d.upper !== null ? +d.upper.toFixed(2) : null; });
    var mid    = bbSeries.map(function (d) { return d.middle !== null ? +d.middle.toFixed(2) : null; });
    var lower  = bbSeries.map(function (d) { return d.lower !== null ? +d.lower.toFixed(2) : null; });

    var bb = computed.bollinger;
    if (bb) {
      $techBbStats.innerHTML =
        '<div class="chart-stat"><span class="chart-stat-value negative">' + escHtml(fmt(bb.upper, 2)) + '</span><span class="chart-stat-label">Superior</span></div>' +
        '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(bb.middle, 2)) + '</span><span class="chart-stat-label">Media</span></div>' +
        '<div class="chart-stat"><span class="chart-stat-value positive">' + escHtml(fmt(bb.lower, 2)) + '</span><span class="chart-stat-label">Inferior</span></div>' +
        '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(bb.percent_b, 2)) + '</span><span class="chart-stat-label">%B</span></div>';
    }

    var opts = baseChartOptions(function (v) { return "$" + v; }, labels);
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      return ctx.dataset.label + ": $" + ctx.parsed.y.toFixed(2);
    };

    charts.techBb = new Chart(document.getElementById("chart-tech-bb"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          { label: "Superior", data: upper, borderColor: CHART_COLORS.negative, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 0, fill: false },
          { label: "Media", data: mid, borderColor: CHART_COLORS.mid, borderWidth: 1.5, pointRadius: 0, fill: false },
          { label: "Inferior", data: lower, borderColor: CHART_COLORS.positive, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 0, fill: "-2", backgroundColor: CHART_COLORS.band },
          { label: "Precio", data: price, borderColor: CHART_COLORS.line, borderWidth: 2, pointRadius: 0, tension: 0.2, fill: false },
        ],
      },
      options: opts,
    });
  }

  /* Volume chart (bar chart with SMA-20 average line) */
  function renderVolumeChart(volumeSeries) {
    destroyChart("volume");
    if (!volumeSeries.length) {
      $volumeStats.innerHTML = '<span class="chart-stat-label">Sin datos de volumen</span>';
      return;
    }

    var labels = volumeSeries.map(function (d) { return d.date; });
    var values = volumeSeries.map(function (d) { return d.value !== null ? +d.value : null; });

    /* SMA-20 del volumen */
    var smaWindow = 20;
    var sma = values.map(function (_, i) {
      if (i < smaWindow - 1) return null;
      var sum = 0;
      for (var j = i - smaWindow + 1; j <= i; j++) sum += (values[j] || 0);
      return sum / smaWindow;
    });

    /* Stats */
    var validVals = values.filter(function (v) { return v !== null; });
    var avgVol = validVals.length ? validVals.reduce(function (a, b) { return a + b; }, 0) / validVals.length : 0;
    var latestVol = validVals.length ? validVals[validVals.length - 1] : 0;

    $volumeStats.innerHTML =
      '<div class="chart-stat">' +
        '<span class="chart-stat-value">' + escHtml(fmtCompact(latestVol)) + '</span>' +
        '<span class="chart-stat-label">Último</span>' +
      '</div>' +
      '<div class="chart-stat">' +
        '<span class="chart-stat-value">' + escHtml(fmtCompact(avgVol)) + '</span>' +
        '<span class="chart-stat-label">Promedio</span>' +
      '</div>';

    var opts = baseChartOptions(function (v) { return fmtCompact(v); }, labels);
    opts.scales.y.min = 0;
    opts.plugins.legend = {
      display: true,
      position: "bottom",
      labels: {
        color: "#586064",
        font: { family: "Inter", size: 11 },
        boxWidth: 12,
        boxHeight: 2,
        padding: 16,
      },
    };
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      return ctx.dataset.label + ": " + fmtCompact(ctx.parsed.y);
    };

    charts.volume = new Chart(document.getElementById("chart-volume"), {
      type: "bar",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          {
            label: "Volumen",
            data: values,
            backgroundColor: CHART_COLORS.volume,
            borderWidth: 0,
            borderRadius: 1,
            order: 2,
          },
          {
            label: "SMA 20d",
            data: sma,
            type: "line",
            borderColor: CHART_COLORS.volumeAvg,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: false,
            order: 1,
          },
        ],
      },
      options: opts,
    });
  }

  /* Format large numbers compactly: 1.2M, 350K, etc. */
  function fmtCompact(n) {
    if (n === null || n === undefined) return "N/A";
    if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
    return String(Math.round(n));
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

  /* Price chart toggle (candle / line) */
  document.querySelectorAll("#price-chart-toggle .toggle-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mode = btn.dataset.mode;
      if (mode === priceChartMode) return;
      priceChartMode = mode;
      document.querySelectorAll("#price-chart-toggle .toggle-btn").forEach(function (b) {
        b.classList.toggle("toggle-btn--active", b.dataset.mode === mode);
      });
      /* Re-render if data available */
      var series = (state.timeseriesResult && state.timeseriesResult.series) || {};
      if (series.ohlc || series.bollinger || series.prices) {
        renderPriceChart(series.ohlc || [], series.bollinger || [], series.prices || []);
      }
    });
  });

  /* Empty state chip clicks */
  document.querySelectorAll(".empty-chip[data-ticker]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $ticker.value = chip.dataset.ticker;
      runAnalysis();
    });
  });

  /* Double-click on any chart canvas resets zoom */
  document.querySelectorAll("canvas[id^='chart-']").forEach(function (canvas) {
    canvas.addEventListener("dblclick", function () {
      var chartInstance = Chart.getChart(canvas);
      if (!chartInstance) return;
      /* Reset Y-axis auto-scale limits before resetting zoom */
      if (chartInstance.scales.y) {
        delete chartInstance.scales.y.options.min;
        delete chartInstance.scales.y.options.max;
      }
      if (chartInstance.resetZoom) chartInstance.resetZoom();
    });
  });

  /* ─── Init ─── */
  $ticker.focus();
  checkHealth();
  setInterval(checkHealth, 30000);

})();
