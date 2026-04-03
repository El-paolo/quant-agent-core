/* ============================================================
   FINA — State, Constants, Helpers, DOM References
   ============================================================ */

(() => {
  "use strict";

  /* ─── Register zoom plugin ─── */
  if (window.ChartZoom) Chart.register(window.ChartZoom);

  /* ─── Candlestick wick plugin (draws high/low lines on floating bars) ─── */
  const candleWickPlugin = {
    id: "candleWick",
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !chart.data.datasets[0]._ohlc) return;
      const ctx = chart.ctx;
      const ohlc = chart.data.datasets[0]._ohlc;
      ctx.save();
      ctx.lineWidth = 1.2;
      meta.data.forEach((bar, i) => {
        if (!ohlc[i]) return;
        const high = chart.scales.y.getPixelForValue(ohlc[i].high);
        const low  = chart.scales.y.getPixelForValue(ohlc[i].low);
        const x    = bar.x;
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
  const ALL_METRICS = [
    "returns", "volatility", "rolling_volatility", "sharpe",
    "sortino", "rsi", "macd", "bollinger", "beta"
  ];

  const CHART_COLORS = {
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
  const state = {
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
    comparisonResult: null,
    loading: { analysis: false, agent: false, timeseries: false, models: false },
    errors: [],
    /* Backtest */
    backtestResult: null,
    /* Assistant */
    chatMessages: [],
    chatOpen: false,
  };

  /* Chart instances — destroyed before re-creating */
  const charts = { vol: null, bb: null, volume: null, rsi: null, macd: null, techBb: null, price: null, garchVol: null, garchForecast: null, hmmRegimes: null, hmmDist: null, btEquity: null, btPositions: null };
  let priceChartMode = "candle";

  /* ─── DOM refs ─── */
  const $ = {
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
    arimaDiagSubtitle:     document.getElementById("arima-diag-subtitle"),
    arimaDiagnostics:      document.getElementById("arima-diagnostics"),
    modelsDiagnostics:     document.getElementById("models-diagnostics"),
    comparisonTable:       document.getElementById("comparison-table"),
    comparisonVerdict:     document.getElementById("comparison-verdict"),
    modelsValidation:      document.getElementById("models-validation"),
    modelsWarnings:        document.getElementById("models-warnings"),
    modelsWarningsInner:   document.getElementById("models-warnings-inner"),
    /* Methodology panel */
    methodologyPanel:    document.getElementById("methodology-panel"),
    backtestPanel:       document.getElementById("backtest-panel"),
    /* Assistant drawer */
    assistantFab:      document.getElementById("assistant-fab"),
    assistantDrawer:   document.getElementById("assistant-drawer"),
    assistantClose:    document.getElementById("assistant-close"),
    assistantMessages: document.getElementById("assistant-messages"),
    assistantForm:     document.getElementById("assistant-form"),
    assistantInput:    document.getElementById("assistant-input"),
    assistantSend:     document.getElementById("assistant-send"),
    /* Backtest */
    btTrainStart:    document.getElementById("bt-train-start"),
    btTrainEnd:      document.getElementById("bt-train-end"),
    btTestStart:     document.getElementById("bt-test-start"),
    btTestEnd:       document.getElementById("bt-test-end"),
    btUseArima:      document.getElementById("bt-use-arima"),
    btUseHmm:        document.getElementById("bt-use-hmm"),
    btUseGarch:      document.getElementById("bt-use-garch"),
    btCapital:       document.getElementById("bt-capital"),
    btRun:           document.getElementById("bt-run"),
    btLoading:       document.getElementById("bt-loading"),
    btError:         document.getElementById("bt-error"),
    btErrorMsg:      document.getElementById("bt-error-msg"),
    btResults:       document.getElementById("bt-results"),
    btPeriodsRow:    document.getElementById("bt-periods-row"),
    btMetricsGrid:   document.getElementById("bt-metrics-grid"),
    btBenchmarkRow:  document.getElementById("bt-benchmark-row"),
    btTradesWrap:    document.getElementById("bt-trades-wrap"),
    btSignalsSummary:document.getElementById("bt-signals-summary"),
    btWarnings:      document.getElementById("bt-warnings"),
    btWarningsInner: document.getElementById("bt-warnings-inner"),
    btPanelTicker:   document.getElementById("backtest-panel-ticker"),
    btPanelMeta:     document.getElementById("backtest-panel-meta"),
    /* Rail */
    railLinks: document.querySelectorAll(".rail-link[data-panel]"),
  };

  /* ─── Helpers ─── */
  const TICKER_RE = /^[A-Z0-9\-=.]{1,20}$/;

  const show = (el) => el.classList.remove("hidden");
  const hide = (el) => el.classList.add("hidden");

  const fmt = (value, decimals) => {
    if (value === null || value === undefined || isNaN(value)) return "N/A";
    return Number(value).toFixed(decimals === undefined ? 2 : decimals);
  };

  const fmtPct = (value, decimals) => {
    if (value === null || value === undefined || isNaN(value)) return "N/A";
    return `${(Number(value) * 100).toFixed(decimals === undefined ? 1 : decimals)}%`;
  };

  const fmtSign = (value, decimals) => {
    if (value === null || value === undefined || isNaN(value)) return "N/A";
    const n = Number(value) * 100;
    const prefix = n >= 0 ? "+" : "";
    return `${prefix}${n.toFixed(decimals === undefined ? 1 : decimals)}%`;
  };

  const fmtCompact = (n) => {
    if (n === null || n === undefined) return "N/A";
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return String(Math.round(n));
  };

  const sentiment = (value) => {
    if (value === null || value === undefined || isNaN(value)) return "na";
    return Number(value) >= 0 ? "positive" : "negative";
  };

  const escHtml = (str) => {
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  };

  /* ─── Expose namespace ─── */
  window.FINA = {
    ALL_METRICS,
    CHART_COLORS,
    TICKER_RE,
    state,
    charts,
    priceChartMode,
    $,
    show,
    hide,
    fmt,
    fmtPct,
    fmtSign,
    fmtCompact,
    sentiment,
    escHtml,
    /* Populated by other modules */
    setPriceChartMode: (m) => { priceChartMode = m; window.FINA.priceChartMode = m; },
    getPriceChartMode: () => priceChartMode,
  };
})();
