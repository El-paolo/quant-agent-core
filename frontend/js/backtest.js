/* ============================================================
   FINA — Backtest Panel
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
  const escHtml = F.escHtml;
  const charts = F.charts;

  /* ─── Default dates ─── */
  const today = new Date();
  const fmt2 = (n) => String(n).padStart(2, "0");
  const isoDate = (d) => `${d.getFullYear()}-${fmt2(d.getMonth() + 1)}-${fmt2(d.getDate())}`;

  const testEnd = new Date(today);
  const testStart = new Date(today);
  testStart.setMonth(testStart.getMonth() - 6);
  const trainEnd = new Date(testStart);
  trainEnd.setDate(trainEnd.getDate() - 1);
  const trainStart = new Date(trainEnd);
  trainStart.setFullYear(trainStart.getFullYear() - 2);

  $.btTrainStart.value = isoDate(trainStart);
  $.btTrainEnd.value = isoDate(trainEnd);
  $.btTestStart.value = isoDate(testStart);
  $.btTestEnd.value = isoDate(testEnd);

  /* ─── Enable run button when ticker is set ─── */
  const updateRunBtn = () => {
    $.btRun.disabled = !state.analysisResult;
  };

  /* ─── Load backtest panel ─── */
  const loadBacktestPanel = () => {
    if (state.analysisResult) {
      $.btPanelTicker.textContent = `Backtest — ${state.ticker}`;
      $.btPanelMeta.textContent = "Simulación de estrategia";
    }
    updateRunBtn();

    if (state.backtestResult && state.backtestResult.ticker === state.ticker) {
      renderBacktestResults(state.backtestResult);
    }
  };

  /* ─── Run backtest ─── */
  const runBacktest = () => {
    const models = [];
    if ($.btUseArima.checked) models.push("arima");
    if ($.btUseHmm.checked) models.push("hmm");
    if ($.btUseGarch.checked) models.push("garch");

    if (models.length === 0) {
      $.btErrorMsg.textContent = "Selecciona al menos un modelo";
      show($.btError);
      return;
    }

    hide($.btResults);
    hide($.btError);
    show($.btLoading);
    $.btRun.disabled = true;

    const body = {
      ticker: state.ticker,
      train_start: $.btTrainStart.value,
      train_end: $.btTrainEnd.value,
      test_start: $.btTestStart.value,
      test_end: $.btTestEnd.value,
      models,
      initial_capital: parseFloat($.btCapital.value) || 10000,
    };

    fetch("/backtest/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      })
      .then((data) => {
        state.backtestResult = data;
        hide($.btLoading);
        renderBacktestResults(data);
        $.btRun.disabled = false;
      })
      .catch((err) => {
        hide($.btLoading);
        $.btErrorMsg.textContent = err.message;
        show($.btError);
        $.btRun.disabled = false;
      });
  };

  /* ─── Render backtest results ─── */
  const renderBacktestResults = (data) => {
    show($.btResults);

    // Periods row
    $.btPeriodsRow.innerHTML =
      `<div class="bt-period-card">` +
        `<div class="bt-period-label">Entrenamiento</div>` +
        `<div class="bt-period-value">${escHtml(data.train_period.start)} → ${escHtml(data.train_period.end)}</div>` +
        `<div class="bt-period-detail">${data.train_period.trading_days} días</div>` +
      `</div>` +
      `<div class="bt-period-card">` +
        `<div class="bt-period-label">Prueba</div>` +
        `<div class="bt-period-value">${escHtml(data.test_period.start)} → ${escHtml(data.test_period.end)}</div>` +
        `<div class="bt-period-detail">${data.test_period.trading_days} días</div>` +
      `</div>`;

    // Equity chart
    renderEquityChart(data.equity_curve, data.benchmark_curve);

    // Metrics cards
    renderMetrics(data.metrics);

    // Benchmark row
    renderBenchmark(data.metrics.benchmark, data.metrics.relative);

    // Positions chart
    renderPositionsChart(data.positions);

    // Trades table
    renderTrades(data.trades);

    // Signals summary
    renderSignalsSummary(data.signals);

    // Warnings
    if (data.warnings && data.warnings.length > 0) {
      $.btWarningsInner.innerHTML = data.warnings.map((w) =>
        `<div class="warning-item"><span class="warning-icon">!</span><span>${escHtml(w)}</span></div>`
      ).join("");
      show($.btWarnings);
    } else {
      hide($.btWarnings);
    }
  };

  /* ─── Equity Chart ─── */
  const renderEquityChart = (equity, benchmark) => {
    if (charts.btEquity) charts.btEquity.destroy();

    const labels = equity.map((p) => p.date);
    const ctx = document.getElementById("chart-bt-equity").getContext("2d");

    charts.btEquity = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Estrategia",
            data: equity.map((p) => p.value),
            borderColor: "#4fc3f7",
            backgroundColor: "rgba(79,195,247,0.08)",
            fill: true,
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1,
          },
          {
            label: "Buy & Hold",
            data: benchmark.map((p) => p.value),
            borderColor: "#aaa",
            borderDash: [4, 3],
            borderWidth: 1.2,
            pointRadius: 0,
            fill: false,
            tension: 0.1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#c0c5c8", font: { size: 11 } } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: $${c.parsed.y.toFixed(2)}` } },
        },
        scales: {
          x: { ticks: { color: "#8a9194", maxTicksLimit: 8, font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
          y: { ticks: { color: "#8a9194", callback: (v) => `$${v.toLocaleString()}`, font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
        },
      },
    });
  };

  /* ─── Metrics Cards ─── */
  const renderMetrics = (metrics) => {
    const s = metrics.strategy;
    const sentiment = (v) => v > 0 ? "positive" : v < 0 ? "negative" : "neutral";

    const cards = [
      { label: "Retorno total", value: fmtSign(s.total_return), cls: sentiment(s.total_return) },
      { label: "Retorno anual.", value: fmtSign(s.annualized_return), cls: sentiment(s.annualized_return) },
      { label: "Sharpe", value: fmt(s.sharpe_ratio, 2), cls: sentiment(s.sharpe_ratio) },
      { label: "Sortino", value: fmt(s.sortino_ratio, 2), cls: sentiment(s.sortino_ratio) },
      { label: "Max Drawdown", value: fmtPct(s.max_drawdown), cls: "negative" },
      { label: "Calmar", value: fmt(s.calmar_ratio, 2), cls: sentiment(s.calmar_ratio) },
      { label: "Win Rate", value: fmtPct(s.win_rate), cls: s.win_rate > 0.5 ? "positive" : "neutral" },
      { label: "Trades", value: s.total_trades, cls: "neutral" },
    ];

    $.btMetricsGrid.innerHTML = cards.map((c) =>
      `<div class="metric-card">` +
        `<div class="mc-label">${escHtml(c.label)}</div>` +
        `<div class="mc-value ${c.cls}">${escHtml(String(c.value))}</div>` +
      `</div>`
    ).join("");
  };

  /* ─── Benchmark Row ─── */
  const renderBenchmark = (bm, rel) => {
    const sentiment = (v) => v > 0 ? "positive" : v < 0 ? "negative" : "neutral";
    $.btBenchmarkRow.innerHTML =
      `<div class="bt-bm-item"><span class="bt-bm-label">Retorno B&H</span><span class="bt-bm-value ${sentiment(bm.total_return)}">${fmtSign(bm.total_return)}</span></div>` +
      `<div class="bt-bm-item"><span class="bt-bm-label">Sharpe B&H</span><span class="bt-bm-value">${fmt(bm.sharpe_ratio, 2)}</span></div>` +
      `<div class="bt-bm-item"><span class="bt-bm-label">Max DD B&H</span><span class="bt-bm-value negative">${fmtPct(bm.max_drawdown)}</span></div>` +
      `<div class="bt-bm-item"><span class="bt-bm-label">Exceso ret.</span><span class="bt-bm-value ${sentiment(rel.excess_return)}">${fmtSign(rel.excess_return)}</span></div>` +
      `<div class="bt-bm-item"><span class="bt-bm-label">Info Ratio</span><span class="bt-bm-value">${fmt(rel.information_ratio, 2)}</span></div>`;
  };

  /* ─── Positions Chart ─── */
  const renderPositionsChart = (positions) => {
    if (charts.btPositions) charts.btPositions.destroy();

    const ctx = document.getElementById("chart-bt-positions").getContext("2d");
    charts.btPositions = new Chart(ctx, {
      type: "bar",
      data: {
        labels: positions.map((p) => p.date),
        datasets: [{
          label: "Posición",
          data: positions.map((p) => p.value),
          backgroundColor: positions.map((p) =>
            p.value > 0 ? "rgba(79,195,247,0.6)" :
            p.value < 0 ? "rgba(239,83,80,0.6)" :
            "rgba(150,150,150,0.3)"
          ),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => `Posición: ${c.parsed.y.toFixed(2)}` } },
        },
        scales: {
          x: { ticks: { color: "#8a9194", maxTicksLimit: 8, font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
          y: { ticks: { color: "#8a9194", font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
        },
      },
    });
  };

  /* ─── Trades Table ─── */
  const renderTrades = (trades) => {
    if (!trades || trades.length === 0) {
      $.btTradesWrap.innerHTML = '<p class="mc-detail">Sin trades registrados</p>';
      return;
    }

    const rows = trades.map((t) => {
      const cls = t.pnl_pct > 0 ? "positive" : t.pnl_pct < 0 ? "negative" : "";
      return `<tr>` +
        `<td>${escHtml(t.entry_date)}</td>` +
        `<td>${escHtml(t.exit_date)}</td>` +
        `<td>${escHtml(t.direction)}</td>` +
        `<td class="${cls}">${fmtSign(t.pnl_pct)}</td>` +
        `<td>${t.duration_days}d</td>` +
      `</tr>`;
    }).join("");

    $.btTradesWrap.innerHTML =
      `<table class="comparison-tbl">` +
        `<thead><tr><th>Entrada</th><th>Salida</th><th>Dir.</th><th>P&L</th><th>Duración</th></tr></thead>` +
        `<tbody>${rows}</tbody>` +
      `</table>`;
  };

  /* ─── Signals Summary ─── */
  const renderSignalsSummary = (signals) => {
    let html = "";
    if (signals.arima) {
      const a = signals.arima;
      html += `<div class="bt-signal-card"><strong>ARIMA</strong> (${a.order.join(",")}) — ` +
        `${a.long_days} long · ${a.short_days} short · ${a.hold_days} hold</div>`;
    }
    if (signals.hmm) {
      const h = signals.hmm;
      html += `<div class="bt-signal-card"><strong>HMM</strong> — ` +
        `${h.long_days} long · ${h.hold_days} hold · ${h.risk_off_days} risk-off</div>`;
    }
    if (signals.garch) {
      const g = signals.garch;
      html += `<div class="bt-signal-card"><strong>GARCH</strong> — ` +
        `sizing avg ${g.avg_sizing} [${g.min_sizing} — ${g.max_sizing}]</div>`;
    }
    $.btSignalsSummary.innerHTML = html || '<p class="mc-detail">Sin señales</p>';
  };

  /* ─── Monte Carlo ─── */

  const runMonteCarlo = () => {
    if (!state.backtestResult) return;

    const n = parseInt($.btMcN.value, 10);
    if (isNaN(n) || n < 50 || n > 300) {
      $.btMcErrorMsg.textContent = "Simulaciones debe estar entre 50 y 300";
      show($.btMcError);
      return;
    }

    hide($.btMcResults);
    hide($.btMcError);
    show($.btMcLoading);
    $.btMcRun.disabled = true;

    const body = {
      ticker: state.ticker,
      train_start: $.btTrainStart.value,
      train_end: $.btTrainEnd.value,
      test_start: $.btTestStart.value,
      test_end: $.btTestEnd.value,
      models: state.backtestResult.models_used,
      initial_capital: parseFloat($.btCapital.value) || 10000,
      n_simulations: n,
    };

    fetch("/backtest/montecarlo/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || `Error ${r.status}`); });
        return r.json();
      })
      .then((data) => {
        state.monteCarloResult = data;
        hide($.btMcLoading);
        renderMonteCarloResults(data);
        $.btMcRun.disabled = false;
      })
      .catch((err) => {
        hide($.btMcLoading);
        $.btMcErrorMsg.textContent = err.message;
        show($.btMcError);
        $.btMcRun.disabled = false;
      });
  };

  const renderMonteCarloResults = (data) => {
    show($.btMcResults);
    renderMCFanChart(data.fan_chart, parseFloat($.btCapital.value) || 10000);
    renderMCRiskCards(data.metrics_distribution, data.n_simulations);
    renderMCDistGrid(data.metrics_distribution);

    if (data.warnings && data.warnings.length > 0) {
      $.btMcWarningsInner.innerHTML = data.warnings.map((w) =>
        `<div class="warning-item"><span class="warning-icon">!</span><span>${escHtml(w)}</span></div>`
      ).join("");
      show($.btMcWarnings);
    } else {
      hide($.btMcWarnings);
    }
  };

  const renderMCFanChart = (fanChart, initialCapital) => {
    if (charts.btMcFan) charts.btMcFan.destroy();

    const labels = fanChart.map((d) => d.date);
    const p5  = fanChart.map((d) => d.p5);
    const p25 = fanChart.map((d) => d.p25);
    const p50 = fanChart.map((d) => d.p50);
    const p75 = fanChart.map((d) => d.p75);
    const p95 = fanChart.map((d) => d.p95);

    const ctx = document.getElementById("chart-bt-mc-fan").getContext("2d");
    charts.btMcFan = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "P95 (optimista)",
            data: p95,
            borderColor: "#34d399",
            backgroundColor: "rgba(52,211,153,0.08)",
            fill: "+1",
            borderWidth: 1.2,
            pointRadius: 0,
            tension: 0.2,
          },
          {
            label: "P75",
            data: p75,
            borderColor: "#6ee7b7",
            backgroundColor: "rgba(110,231,183,0.10)",
            fill: "+1",
            borderWidth: 1,
            pointRadius: 0,
            tension: 0.2,
          },
          {
            label: "P50 (mediana)",
            data: p50,
            borderColor: "#f5f5f5",
            backgroundColor: "rgba(245,245,245,0.06)",
            fill: "+1",
            borderWidth: 2.2,
            pointRadius: 0,
            tension: 0.2,
          },
          {
            label: "P25",
            data: p25,
            borderColor: "#fbbf24",
            backgroundColor: "rgba(251,191,36,0.10)",
            fill: "+1",
            borderWidth: 1,
            pointRadius: 0,
            tension: 0.2,
          },
          {
            label: "P5 (pesimista)",
            data: p5,
            borderColor: "#f87171",
            backgroundColor: "rgba(248,113,113,0.08)",
            fill: false,
            borderWidth: 1.2,
            pointRadius: 0,
            tension: 0.2,
          },
          {
            label: "Capital inicial",
            data: new Array(labels.length).fill(initialCapital),
            borderColor: "rgba(255,255,255,0.20)",
            borderDash: [4, 4],
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            labels: {
              color: "#c0c5c8",
              font: { size: 10 },
              filter: (item) => item.text !== "P75" && item.text !== "P25",
            },
          },
          tooltip: {
            callbacks: {
              label: (c) => `${c.dataset.label}: $${c.parsed.y.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
            },
          },
        },
        scales: {
          x: { ticks: { color: "#8a9194", maxTicksLimit: 8, font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
          y: { ticks: { color: "#8a9194", callback: (v) => `$${v.toLocaleString()}`, font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.04)" } },
        },
      },
    });
  };

  const renderMCRiskCards = (md, nSims) => {
    const varPct = (md.var_95 * 100).toFixed(1);
    const cvarPct = (md.cvar_95 * 100).toFixed(1);
    const probProfit = (md.prob_profit * 100).toFixed(0);
    const probBeat = (md.prob_beat_benchmark * 100).toFixed(0);

    $.btMcRiskRow.innerHTML =
      `<div class="bt-mc-risk-card">` +
        `<div class="bt-mc-risk-label">VaR 95%</div>` +
        `<div class="bt-mc-risk-value negative">${varPct}%</div>` +
        `<div class="bt-mc-risk-detail">Pérdida máx. esperada 95% de las sims</div>` +
      `</div>` +
      `<div class="bt-mc-risk-card">` +
        `<div class="bt-mc-risk-label">CVaR 95%</div>` +
        `<div class="bt-mc-risk-value negative">${cvarPct}%</div>` +
        `<div class="bt-mc-risk-detail">Pérdida promedio en el 5% peor de sims</div>` +
      `</div>` +
      `<div class="bt-mc-risk-card">` +
        `<div class="bt-mc-risk-label">Prob. ganancia</div>` +
        `<div class="bt-mc-risk-value ${parseInt(probProfit, 10) >= 50 ? "positive" : "negative"}">${probProfit}%</div>` +
        `<div class="bt-mc-risk-detail">Sims que terminan en positivo</div>` +
      `</div>` +
      `<div class="bt-mc-risk-card">` +
        `<div class="bt-mc-risk-label">Prob. superar B&H</div>` +
        `<div class="bt-mc-risk-value ${parseInt(probBeat, 10) >= 50 ? "positive" : "negative"}">${probBeat}%</div>` +
        `<div class="bt-mc-risk-detail">Sims que superan Buy & Hold</div>` +
      `</div>` +
      `<div class="bt-mc-risk-card">` +
        `<div class="bt-mc-risk-label">Simulaciones</div>` +
        `<div class="bt-mc-risk-value">${nSims}</div>` +
        `<div class="bt-mc-risk-detail">Trayectorias usadas en la agregación</div>` +
      `</div>`;
  };

  const renderMCDistGrid = (md) => {
    const fmtPerc = (v) => `${(v * 100).toFixed(1)}%`;

    const items = [
      {
        label: "Retorno total",
        p5:  fmtPerc(md.total_return.p5),
        p50: fmtPerc(md.total_return.p50),
        p95: fmtPerc(md.total_return.p95),
        pos: md.total_return.p50 >= 0,
      },
      {
        label: "Max Drawdown",
        p5:  fmtPerc(md.max_drawdown.p5),
        p50: fmtPerc(md.max_drawdown.p50),
        p95: fmtPerc(md.max_drawdown.p95),
        pos: false,
      },
      {
        label: "Sharpe",
        p5:  md.sharpe_ratio.p5.toFixed(2),
        p50: md.sharpe_ratio.p50.toFixed(2),
        p95: md.sharpe_ratio.p95.toFixed(2),
        pos: md.sharpe_ratio.p50 >= 0,
      },
    ];

    $.btMcDistGrid.innerHTML = items.map((item) =>
      `<div class="bt-mc-dist-card">` +
        `<div class="bt-mc-dist-label">${escHtml(item.label)}</div>` +
        `<div class="bt-mc-dist-row">` +
          `<div class="bt-mc-dist-cell"><span class="bt-mc-perc-label">P5</span><span class="bt-mc-perc-val">${escHtml(item.p5)}</span></div>` +
          `<div class="bt-mc-dist-cell highlight"><span class="bt-mc-perc-label">P50</span><span class="bt-mc-perc-val ${item.pos ? "positive" : "negative"}">${escHtml(item.p50)}</span></div>` +
          `<div class="bt-mc-dist-cell"><span class="bt-mc-perc-label">P95</span><span class="bt-mc-perc-val">${escHtml(item.p95)}</span></div>` +
        `</div>` +
      `</div>`
    ).join("");
  };

  /* ─── Expose ─── */
  F.loadBacktestPanel = loadBacktestPanel;

  /* ─── Event Handlers ─── */
  $.btRun.addEventListener("click", runBacktest);
  $.btMcRun.addEventListener("click", runMonteCarlo);
})();
