/* ============================================================
   FINA — API Calls, Navigation, Analysis Orchestration
   ============================================================ */

(() => {
  "use strict";

  const F = window.FINA;
  const state = F.state;
  const $ = F.$;
  const show = F.show;
  const hide = F.hide;

  /* ─── Multi-ticker tag input ─── */
  const addTicker = (raw) => {
    const t = raw.trim().toUpperCase();
    if (!t || !F.TICKER_RE.test(t)) return false;
    if (state.tickers.includes(t)) return false;
    state.tickers.push(t);
    state.ticker = state.tickers[0];
    renderTickerTags();
    return true;
  };

  const removeTicker = (t) => {
    state.tickers = state.tickers.filter((x) => x !== t);
    state.ticker = state.tickers[0] || "";
    renderTickerTags();
  };

  const renderTickerTags = () => {
    $.tickerTags.innerHTML = state.tickers.map((t) =>
      `<span class="cb-ticker-tag">${t}<button class="cb-tag-x" data-ticker="${t}" type="button">&times;</button></span>`
    ).join("");

    // Badge
    if (state.tickers.length > 1) show($.portfolioBadge);
    else hide($.portfolioBadge);

    // Placeholder
    $.ticker.placeholder = state.tickers.length > 0 ? "Otro ticker..." : "AAPL";

    // Update portfolio run button + pipeline steps
    if (F.updatePfRunBtn) F.updatePfRunBtn();
    updatePipelineSteps();
  };

  // Tag remove handler (delegated)
  $.tickerTags.addEventListener("click", (e) => {
    const btn = e.target.closest(".cb-tag-x");
    if (btn) {
      removeTicker(btn.dataset.ticker);
    }
  });

  // Comma to add ticker, Enter to add + run, Backspace to remove last
  $.ticker.addEventListener("keydown", (e) => {
    if (e.key === ",") {
      e.preventDefault();
      const raw = $.ticker.value.trim();
      if (raw) {
        addTicker(raw);
        $.ticker.value = "";
      }
    }
    // Enter is handled by panels.js (calls runAnalysis which flushes)
    if (e.key === "Backspace" && $.ticker.value === "" && state.tickers.length > 0) {
      removeTicker(state.tickers[state.tickers.length - 1]);
    }
  });

  /* ─── Ticker validation (backward compat) ─── */
  const validateTicker = () => {
    const raw = $.ticker.value.trim().toUpperCase();
    $.ticker.value = raw;
    // Only visual feedback — don't add ticker on every keystroke
    $.ticker.classList.toggle("invalid", raw.length > 0 && !F.TICKER_RE.test(raw));
    if (state.tickers.length === 0 && !raw) return null;
    return state.tickers[0] || raw || null;
  };

  /* Flush pending input into tags (called before analysis) */
  const flushTickerInput = () => {
    const raw = $.ticker.value.trim().toUpperCase();
    if (raw && F.TICKER_RE.test(raw)) {
      addTicker(raw);
      $.ticker.value = "";
    }
  };

  /* ─── Health check ─── */
  const checkHealth = () => {
    fetch("/health")
      .then((r) => r.json())
      .then((data) => {
        $.healthDot.className = "health-dot online";
        $.healthLbl.textContent = `v${data.version}`;
      })
      .catch(() => {
        $.healthDot.className = "health-dot offline";
        $.healthLbl.textContent = "offline";
      });
  };

  /* ─── Pipeline step state management ─── */
  const STEP_PREREQS = {
    1: () => true,                          // Universo: always available
    2: () => !!state.analysisResult,        // Exploración: needs analysis
    3: () => !!state.analysisResult,        // Modelos: needs analysis
    4: () => !!state.analysisResult,        // Backtest: needs analysis
    5: () => state.tickers.length >= 2,     // Portfolio: needs 2+ tickers
    6: () => !!state.analysisResult,        // Predicciones: needs prior analysis
  };

  const updatePipelineSteps = () => {
    document.querySelectorAll(".rail-step[data-step]").forEach((btn) => {
      const step = parseInt(btn.dataset.step, 10);
      const unlocked = STEP_PREREQS[step] ? STEP_PREREQS[step]() : true;
      btn.classList.toggle("rail-step--locked", !unlocked);
      btn.disabled = !unlocked;
    });
  };

  /* ─── Next step CTA handler (delegated) ─── */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".pipeline-next-btn[data-goto]");
    if (btn) {
      const target = btn.dataset.goto;
      switchToPanel(target);
    }
  });

  /* ─── Read selected metrics ─── */
  const readSelectedMetrics = () => {
    const checks = $.paramsBody.querySelectorAll('input[type="checkbox"]');
    const selected = [];
    checks.forEach((cb) => { if (cb.checked) selected.push(cb.value); });
    return selected;
  };

  /* ─── Panel Navigation ─── */
  const setActiveRailLink = (panelName) => {
    $.railLinks.forEach((link) => {
      const isActive = link.dataset.panel === panelName;
      link.classList.toggle("rail-link--active", isActive);
      if (isActive) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  };

  const switchToPanel = (panelName) => {
    /* Check if step is locked */
    const stepBtn = document.querySelector(`.rail-step[data-panel="${panelName}"]`);
    if (stepBtn && stepBtn.classList.contains("rail-step--locked")) return;

    const prevPanel = state.activePanel;

    /* Destroy charts when leaving panels */
    if (prevPanel === "metrics" && panelName !== "metrics") {
      ["price", "vol", "bb", "volume"].forEach(F.destroyChart);
    }
    if (prevPanel === "technicals" && panelName !== "technicals") {
      ["rsi", "macd", "techBb"].forEach(F.destroyChart);
    }
    if (prevPanel === "models" && panelName !== "models") {
      ["garchVol", "garchForecast", "hmmRegimes", "hmmDist"].forEach(F.destroyChart);
    }
    if (prevPanel === "backtest" && panelName !== "backtest") {
      ["btEquity", "btPositions", "btMcFan"].forEach(F.destroyChart);
    }
    if (prevPanel === "portfolio" && panelName !== "portfolio") {
      ["pfEquity"].forEach(F.destroyChart);
    }

    /* Hide all panels */
    hide($.emptyState);
    hide($.loadingState);
    hide($.errorState);
    hide($.resultsState);
    hide($.metricsPanel);
    hide($.techPanel);
    hide($.modelsPanel);
    hide($.newsPanel);
    hide($.backtestPanel);
    hide($.portfolioPanel);
    hide($.predictionsPanel);
    hide($.methodologyPanel);

    state.activePanel = panelName;
    setActiveRailLink(panelName);

    if (panelName === "overview") {
      if (!state.analysisResult) show($.emptyState);
      else show($.resultsState);
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
    } else if (panelName === "models") {
      show($.modelsPanel);
      if (state.analysisResult) {
        F.loadModelsPanel();
      } else {
        hide($.modelsPanelLoading);
        hide($.modelsPanelContent);
        hide($.modelsPanelError);
        hide($.modelsPanelEmpty);
        $.modelsPanelTicker.textContent = "";
        $.modelsPanelMeta.textContent = "Ingresa un ticker y presiona Analizar";
        show($.modelsPanelEmpty);
      }
    } else if (panelName === "backtest") {
      show($.backtestPanel);
      F.loadBacktestPanel();
    } else if (panelName === "portfolio") {
      show($.portfolioPanel);
      F.loadPortfolioPanel();
    } else if (panelName === "predictions") {
      show($.predictionsPanel);
      F.loadPredictionsPanel();
    } else if (panelName === "methodology") {
      show($.methodologyPanel);
    }
  };

  /* ─── Active AbortController for cancellable requests ─── */
  let activeController = null;

  /* ─── Run analysis ─── */
  const runAnalysis = () => {
    flushTickerInput();
    const ticker = state.tickers[0] || null;
    if (!ticker) { $.ticker.focus(); return; }

    /* Abort any in-flight request */
    if (activeController) activeController.abort();
    activeController = new AbortController();
    const signal = activeController.signal;

    const tickerChanged = ticker !== state.agentTicker;

    state.ticker  = ticker;
    state.period  = $.period.value;
    state.metrics = readSelectedMetrics();
    state.errors  = [];
    state.analysisResult        = null;
    state.timeseriesResult      = null;
    state.techSeriesResult      = null;
    state.modelsResult          = null;
    state.modelsTimeseriesResult = null;
    state.comparisonResult       = null;
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
    hide($.modelsPanel);
    hide($.newsPanel);
    hide($.backtestPanel);
    hide($.portfolioPanel);
    hide($.methodologyPanel);
    show($.loadingState);

    $.analyzeBtn.disabled = true;
    state.loading.analysis = true;

    const analysisPromise = fetch("/analysis/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: state.ticker, period: state.period, metrics: state.metrics }),
      signal,
    })
      .then((r) => {
        state.processTimeMs = r.headers.get("X-Process-Time-Ms");
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      })
      .then((data) => { state.analysisResult = data; state.loading.analysis = false; })
      .catch((err) => {
        state.loading.analysis = false;
        if (err.name !== "AbortError") state.errors.push(err.message);
      });

    let agentPromise;
    if (tickerChanged) {
      state.loading.agent = true;
      agentPromise = fetch("/agent/summarize/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: state.ticker }),
        signal,
      })
        .then((r) => {
          if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Agent error ${r.status}`); });
          return r.json();
        })
        .then((data) => { state.agentResult = data; state.agentTicker = state.ticker; state.loading.agent = false; })
        .catch(() => { state.loading.agent = false; });
    } else {
      agentPromise = Promise.resolve();
    }

    analysisPromise.then(() => {
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
        updatePipelineSteps();
      }

      agentPromise.then(F.renderAgentResults);
    });
  };

  /* ─── Expose ─── */
  F.addTicker = addTicker;
  F.removeTicker = removeTicker;
  F.validateTicker = validateTicker;
  F.checkHealth = checkHealth;
  F.switchToPanel = switchToPanel;
  F.runAnalysis = runAnalysis;
  F.updatePipelineSteps = updatePipelineSteps;
})();
