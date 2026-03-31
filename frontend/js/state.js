/* ============================================================
   FINA — State, Constants, Helpers, DOM References
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
        ctx.strokeStyle = ohlc[i].close >= ohlc[i].open ? "#006d4a" : "#ba1b24";
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
    line:     "#1a56db",
    positive: "#006d4a",
    negative: "#ba1b24",
    neutral:  "#586064",
    grid:     "rgba(171,179,183,0.18)",
    upper:    "rgba(186,27,36,0.25)",
    lower:    "rgba(0,109,74,0.25)",
    mid:      "#8b5cf6",
    band:     "rgba(139,92,246,0.08)",
    fill:     "rgba(26,86,219,0.10)",
    volume:   "rgba(107,114,128,0.35)",
    volumeAvg:"#f59e0b",
    candleUp:  "#006d4a",
    candleDn:  "#ba1b24",
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
    modelsResult: null,
    modelsTimeseriesResult: null,
    loading: { analysis: false, agent: false, timeseries: false, models: false },
    errors: [],
  };

  /* Chart instances — destroyed before re-creating */
  var charts = { vol: null, bb: null, volume: null, rsi: null, macd: null, techBb: null, price: null, garchVol: null, garchForecast: null, hmmRegimes: null, hmmDist: null };
  var priceChartMode = "candle";

  /* ─── DOM refs ─── */
  var $ = {
    ticker:       document.getElementById("ticker-input"),
    period:       document.getElementById("period-select"),
    analyzeBtn:   document.getElementById("analyze-btn"),
    healthDot:    document.getElementById("health-dot"),
    healthLbl:    document.getElementById("health-label"),
    paramsToggle: document.getElementById("params-toggle"),
    paramsBody:   document.getElementById("params-body"),
    /* Overview */
    emptyState:       document.getElementById("empty-state"),
    loadingState:     document.getElementById("loading-state"),
    errorState:       document.getElementById("error-state"),
    errorMessage:     document.getElementById("error-message"),
    errorRetry:       document.getElementById("error-retry"),
    resultsState:     document.getElementById("results-state"),
    resultsTicker:    document.getElementById("results-ticker"),
    resultsPeriod:    document.getElementById("results-period"),
    resultsTime:      document.getElementById("results-time"),
    metricsGrid:      document.getElementById("metrics-grid"),
    warnings:         document.getElementById("warnings"),
    warningsInner:    document.getElementById("warnings-inner"),
    summaryStatus:    document.getElementById("summary-status"),
    summaryBody:      document.getElementById("summary-body"),
    headlinesSection: document.getElementById("headlines-section"),
    headlinesList:    document.getElementById("headlines-list"),
    /* Metrics panel */
    metricsPanel:        document.getElementById("metrics-panel"),
    metricsPanelTicker:  document.getElementById("metrics-panel-ticker"),
    metricsPanelMeta:    document.getElementById("metrics-panel-meta"),
    metricsPanelLoading: document.getElementById("metrics-panel-loading"),
    metricsPanelError:   document.getElementById("metrics-panel-error"),
    metricsPanelErrorMsg:document.getElementById("metrics-panel-error-msg"),
    metricsPanelContent: document.getElementById("metrics-panel-content"),
    volStats:            document.getElementById("vol-stats"),
    bbStats:             document.getElementById("bb-stats"),
    volumeStats:         document.getElementById("volume-stats"),
    priceStats:          document.getElementById("price-stats"),
    priceChartSubtitle:  document.getElementById("price-chart-subtitle"),
    returnsStatsGrid:    document.getElementById("returns-stats-grid"),
    ratiosGrid:          document.getElementById("ratios-grid"),
    /* News & IA panel */
    newsPanel:           document.getElementById("news-panel"),
    newsPanelTicker:     document.getElementById("news-panel-ticker"),
    newsPanelMeta:       document.getElementById("news-panel-meta"),
    newsPanelEmpty:      document.getElementById("news-panel-empty"),
    newsSummarySection:  document.getElementById("news-summary-section"),
    /* Technicals panel */
    techPanel:           document.getElementById("technicals-panel"),
    techPanelTicker:     document.getElementById("tech-panel-ticker"),
    techPanelMeta:       document.getElementById("tech-panel-meta"),
    techPanelLoading:    document.getElementById("tech-panel-loading"),
    techPanelError:      document.getElementById("tech-panel-error"),
    techPanelErrorMsg:   document.getElementById("tech-panel-error-msg"),
    techPanelContent:    document.getElementById("tech-panel-content"),
    rsiStats:            document.getElementById("rsi-stats"),
    macdStats:           document.getElementById("macd-stats"),
    techBbStats:         document.getElementById("tech-bb-stats"),
    /* Models panel */
    modelsPanel:           document.getElementById("models-panel"),
    modelsPanelTicker:     document.getElementById("models-panel-ticker"),
    modelsPanelMeta:       document.getElementById("models-panel-meta"),
    modelsPanelLoading:    document.getElementById("models-panel-loading"),
    modelsPanelError:      document.getElementById("models-panel-error"),
    modelsPanelErrorMsg:   document.getElementById("models-panel-error-msg"),
    modelsPanelEmpty:      document.getElementById("models-panel-empty"),
    modelsPanelContent:    document.getElementById("models-panel-content"),
    regimeBadge:           document.getElementById("models-regime-badge"),
    regimeDot:             document.getElementById("regime-dot"),
    regimeLabel:           document.getElementById("regime-label"),
    regimeDetail:          document.getElementById("regime-detail"),
    hmmStats:              document.getElementById("hmm-stats"),
    hmmLegend:             document.getElementById("hmm-legend"),
    modelsStateParams:     document.getElementById("models-state-params"),
    garchVolStats:         document.getElementById("garch-vol-stats"),
    garchForecastSubtitle: document.getElementById("garch-forecast-subtitle"),
    garchForecastStats:    document.getElementById("garch-forecast-stats"),
    modelsDiagnostics:     document.getElementById("models-diagnostics"),
    modelsValidation:      document.getElementById("models-validation"),
    modelsWarnings:        document.getElementById("models-warnings"),
    modelsWarningsInner:   document.getElementById("models-warnings-inner"),
    /* Methodology panel */
    methodologyPanel:    document.getElementById("methodology-panel"),
    /* Rail */
    railLinks: document.querySelectorAll(".rail-link[data-panel]"),
  };

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

  function fmtCompact(n) {
    if (n === null || n === undefined) return "N/A";
    if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
    return String(Math.round(n));
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

  /* ─── Expose namespace ─── */
  window.FINA = {
    ALL_METRICS: ALL_METRICS,
    CHART_COLORS: CHART_COLORS,
    TICKER_RE: TICKER_RE,
    state: state,
    charts: charts,
    priceChartMode: priceChartMode,
    $: $,
    show: show,
    hide: hide,
    fmt: fmt,
    fmtPct: fmtPct,
    fmtSign: fmtSign,
    fmtCompact: fmtCompact,
    sentiment: sentiment,
    escHtml: escHtml,
    /* Populated by other modules */
    setPriceChartMode: function (m) { priceChartMode = m; window.FINA.priceChartMode = m; },
    getPriceChartMode: function () { return priceChartMode; },
  };
})();
