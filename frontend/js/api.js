/* ============================================================
   FINA — API Calls, Navigation, Analysis Orchestration
   ============================================================ */

(function () {
  "use strict";

  var F = window.FINA;
  var state = F.state;
  var $ = F.$;
  var show = F.show;
  var hide = F.hide;

  /* ─── Ticker validation ─── */
  function validateTicker() {
    var raw = $.ticker.value.trim().toUpperCase();
    $.ticker.value = raw;
    var valid = raw.length > 0 && F.TICKER_RE.test(raw);
    $.ticker.classList.toggle("invalid", raw.length > 0 && !valid);
    return valid ? raw : null;
  }

  /* ─── Health check ─── */
  function checkHealth() {
    fetch("/health")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        $.healthDot.className = "health-dot online";
        $.healthLbl.textContent = "v" + data.version;
      })
      .catch(function () {
        $.healthDot.className = "health-dot offline";
        $.healthLbl.textContent = "offline";
      });
  }

  /* ─── Read selected metrics ─── */
  function readSelectedMetrics() {
    var checks = $.paramsBody.querySelectorAll('input[type="checkbox"]');
    var selected = [];
    checks.forEach(function (cb) { if (cb.checked) selected.push(cb.value); });
    return selected;
  }

  /* ─── Panel Navigation ─── */
  function setActiveRailLink(panelName) {
    $.railLinks.forEach(function (link) {
      var isActive = link.dataset.panel === panelName;
      link.classList.toggle("rail-link--active", isActive);
      if (isActive) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function switchToPanel(panelName) {
    var prevPanel = state.activePanel;

    /* Destroy charts when leaving metrics or technicals panels */
    if (prevPanel === "metrics" && panelName !== "metrics") {
      ["price", "vol", "bb", "volume"].forEach(F.destroyChart);
    }
    if (prevPanel === "technicals" && panelName !== "technicals") {
      ["rsi", "macd", "techBb"].forEach(F.destroyChart);
    }

    /* Hide all panels */
    hide($.emptyState);
    hide($.loadingState);
    hide($.errorState);
    hide($.resultsState);
    hide($.metricsPanel);
    hide($.techPanel);
    hide($.newsPanel);
    hide($.methodologyPanel);

    state.activePanel = panelName;
    setActiveRailLink(panelName);

    if (panelName === "overview") {
      if (!state.analysisResult) {
        show($.emptyState);
      } else {
        show($.resultsState);
      }
    } else if (panelName === "metrics") {
      show($.metricsPanel);
      if (state.analysisResult) {
        F.loadMetricsPanel();
      } else {
        hide($.metricsPanelLoading);
        hide($.metricsPanelContent);
        hide($.metricsPanelError);
        $.metricsPanelTicker.textContent = "";
        $.metricsPanelMeta.textContent = "Ingresa un ticker y presiona Analizar";
      }
    } else if (panelName === "news") {
      show($.newsPanel);
      if (state.agentResult) {
        $.newsPanelTicker.textContent = state.agentTicker || "";
        $.newsPanelMeta.textContent = "Noticias & Análisis IA";
        hide($.newsPanelEmpty);
        show($.newsSummarySection);
        F.renderAgentResults();
      } else if (state.loading.agent) {
        $.newsPanelTicker.textContent = state.ticker || "";
        $.newsPanelMeta.textContent = "Cargando...";
        hide($.newsPanelEmpty);
        show($.newsSummarySection);
      } else {
        $.newsPanelTicker.textContent = "";
        $.newsPanelMeta.textContent = "Noticias & Análisis IA";
        hide($.newsSummarySection);
        hide($.headlinesSection);
        show($.newsPanelEmpty);
      }
    } else if (panelName === "technicals") {
      show($.techPanel);
      if (state.analysisResult) {
        F.loadTechnicalsPanel();
      } else {
        hide($.techPanelLoading);
        hide($.techPanelContent);
        hide($.techPanelError);
        $.techPanelTicker.textContent = "";
        $.techPanelMeta.textContent = "Ingresa un ticker y presiona Analizar";
      }
    } else if (panelName === "methodology") {
      show($.methodologyPanel);
    }
  }

  /* ─── Active AbortController for cancellable requests ─── */
  var activeController = null;

  /* ─── Run analysis ─── */
  function runAnalysis() {
    var ticker = validateTicker();
    if (!ticker) { $.ticker.focus(); return; }

    /* Abort any in-flight request */
    if (activeController) activeController.abort();
    activeController = new AbortController();
    var signal = activeController.signal;

    var tickerChanged = ticker !== state.agentTicker;

    state.ticker  = ticker;
    state.period  = $.period.value;
    state.metrics = readSelectedMetrics();
    state.errors  = [];
    state.analysisResult    = null;
    state.timeseriesResult  = null;
    state.techSeriesResult  = null;
    if (tickerChanged) state.agentResult = null;
    if (state.metrics.length === 0) state.metrics = F.ALL_METRICS.slice();

    /* Reset to overview loading */
    state.activePanel = "overview";
    setActiveRailLink("overview");
    hide($.emptyState);
    hide($.errorState);
    hide($.resultsState);
    hide($.metricsPanel);
    hide($.techPanel);
    hide($.newsPanel);
    hide($.methodologyPanel);
    show($.loadingState);

    $.analyzeBtn.disabled = true;
    state.loading.analysis = true;

    var analysisPromise = fetch("/analysis/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: state.ticker, period: state.period, metrics: state.metrics }),
      signal: signal,
    })
      .then(function (r) {
        state.processTimeMs = r.headers.get("X-Process-Time-Ms");
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Error " + r.status); });
        return r.json();
      })
      .then(function (data) { state.analysisResult = data; state.loading.analysis = false; })
      .catch(function (err) {
        state.loading.analysis = false;
        if (err.name !== "AbortError") state.errors.push(err.message);
      });

    var agentPromise;
    if (tickerChanged) {
      state.loading.agent = true;
      agentPromise = fetch("/agent/summarize/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: state.ticker }),
        signal: signal,
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
      $.analyzeBtn.disabled = false;

      if (state.errors.length > 0 && !state.analysisResult) {
        $.errorMessage.textContent = state.errors.join("\n");
        hide($.loadingState);
        show($.errorState);
        return;
      }

      if (state.analysisResult) {
        F.renderOverview();
        hide($.loadingState);
        show($.resultsState);
      }

      agentPromise.then(F.renderAgentResults);
    });
  }

  /* ─── Expose ─── */
  F.validateTicker = validateTicker;
  F.checkHealth = checkHealth;
  F.switchToPanel = switchToPanel;
  F.runAnalysis = runAnalysis;
})();
