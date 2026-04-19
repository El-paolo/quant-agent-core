/* ============================================================
   FINA — Chart Rendering (Chart.js)
   ============================================================ */

(() => {
  "use strict";

  const F = window.FINA;
  const charts = F.charts;
  const COLORS = F.CHART_COLORS;
  const escHtml = F.escHtml;
  const fmt = F.fmt;
  const fmtPct = F.fmtPct;
  const fmtSign = F.fmtSign;
  const fmtCompact = F.fmtCompact;
  const sentiment = F.sentiment;
  const $ = F.$;

  /* ─── Pin System ─── */
  const PIN_COLORS = ["#f87171", "#fbbf24", "#34d399", "#a78bfa", "#f472b6", "#38bdf8", "#fb923c", "#4ade80"];
  const PIN_MAX = 8;
  const DOUBLE_CLICK_DELAY = 300;

  // Pin groups: charts that share the same date axis sync pins together
  const pinGroups = {
    technicals: { chartKeys: ["rsi", "macd", "techBb"], pins: [], lastClickTime: 0, lastClickIdx: -1 },
    metrics:    { chartKeys: ["vol", "bb", "volume", "price"], pins: [], lastClickTime: 0, lastClickIdx: -1 },
  };

  const pinLinesPlugin = {
    id: "pinLines",
    afterDraw(chart) {
      const group = chart._pinGroup;
      if (!group || !group.pins.length) return;

      const xScale = chart.scales.x;
      const yScale = chart.scales.y;
      if (!xScale || !yScale) return;

      const ctx = chart.ctx;
      ctx.save();

      for (const pin of group.pins) {
        const x = xScale.getPixelForValue(pin.index);
        if (x < xScale.left || x > xScale.right) continue;

        ctx.strokeStyle = pin.color;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(x, yScale.top);
        ctx.lineTo(x, yScale.bottom);
        ctx.stroke();

        // Date label at top with background
        ctx.fillStyle = pin.color;
        ctx.globalAlpha = 0.9;
        const textWidth = ctx.measureText(pin.date).width;
        ctx.fillRect(x - textWidth / 2 - 3, yScale.top - 16, textWidth + 6, 12);
        ctx.globalAlpha = 1;
        ctx.fillStyle = "#fff";
        ctx.font = "bold 9px Inter, system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(pin.date, x, yScale.top - 5);
      }
      ctx.restore();
    },
  };
  Chart.register(pinLinesPlugin);

  const attachPinGroup = (chartKey, groupName) => {
    const chart = charts[chartKey];
    const group = pinGroups[groupName];
    if (!chart || !group) return;
    chart._pinGroup = group;
  };

  const handlePinClick = (groupName, e, chart) => {
    const group = pinGroups[groupName];
    if (!group) return;

    const xScale = chart.scales.x;
    if (!xScale) return;

    const rect = chart.canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;

    // Find nearest data index
    const idx = Math.round(xScale.getValueForPixel(clickX));
    if (idx < 0 || idx >= chart.data.labels.length) return;

    const now = Date.now();
    const isDoubleClick = (now - group.lastClickTime < DOUBLE_CLICK_DELAY) && (idx === group.lastClickIdx);

    group.lastClickTime = now;
    group.lastClickIdx = idx;

    if (isDoubleClick) {
      // Double-click: remove pin at this index or clear all if 2 clicks on empty area
      const existing = group.pins.findIndex((p) => p.index === idx);
      if (existing !== -1) {
        group.pins.splice(existing, 1);
      } else if (group.pins.length > 0) {
        // Two clicks on empty area with pins → clear all
        group.pins.length = 0;
      }
      group.lastClickTime = 0; // Reset counter
    } else {
      // Single click: add pin if no pins exist
      if (group.pins.length === 0) {
        const fullLabels = chart.data.datasets[0]?.data ? chart._pinFullDates || chart.data.labels : chart.data.labels;
        const date = fullLabels[idx] || `#${idx}`;
        const colorIdx = group.pins.length % PIN_COLORS.length;
        group.pins.push({ index: idx, date: String(date), color: PIN_COLORS[colorIdx] });
      }
    }

    // Redraw all charts in the group
    for (const key of group.chartKeys) {
      if (charts[key]) charts[key].update("none");
    }
  };

  const setupPinListeners = (chartKey, groupName) => {
    const chart = charts[chartKey];
    if (!chart) return;
    chart.canvas.addEventListener("click", (e) => handlePinClick(groupName, e, chart));
  };

  const clearPins = (groupName) => {
    const group = pinGroups[groupName];
    if (!group) return;
    group.pins.length = 0;
    group.lastClickTime = 0;
    group.lastClickIdx = -1;
    for (const key of group.chartKeys) {
      if (charts[key]) charts[key].update("none");
    }
  };

  /* ─── Lifecycle ─── */
  const destroyChart = (key) => {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  };

  const destroyAllCharts = () => {
    Object.keys(charts).forEach(destroyChart);
  };

  /* ─── Auto-scale Y after zoom/pan ─── */
  const autoScaleY = (chart) => {
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    if (!xScale || !yScale) return;

    const minIdx = Math.max(0, Math.floor(xScale.min));
    const maxIdx = Math.min(xScale.max, chart.data.labels.length - 1);
    if (maxIdx <= minIdx) return;

    let yMin = Infinity;
    let yMax = -Infinity;

    chart.data.datasets.forEach((ds) => {
      for (let i = minIdx; i <= maxIdx; i++) {
        const val = ds.data[i];
        if (val === null || val === undefined) continue;
        if (Array.isArray(val)) {
          if (val[0] < yMin) yMin = val[0];
          if (val[1] > yMax) yMax = val[1];
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
    const padding = (yMax - yMin) * 0.05 || 1;
    yScale.options.min = yMin - padding;
    yScale.options.max = yMax + padding;
    chart.update("none");
  };

  /* ─── Shared chart config ─── */
  const baseChartOptions = (yTickFmt, fullDates) => ({
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
          title: (items) => {
            if (!items.length) return "";
            const idx = items[0].dataIndex;
            return fullDates && fullDates[idx] ? fullDates[idx] : items[0].label;
          },
        },
      },
      zoom: {
        pan: {
          enabled: true,
          mode: "xy",
          onPanComplete: (ctx) => autoScaleY(ctx.chart),
        },
        zoom: {
          wheel: { enabled: true, speed: 0.1 },
          pinch: { enabled: true },
          mode: "xy",
          onZoomComplete: (ctx) => autoScaleY(ctx.chart),
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
        grid: { color: COLORS.grid },
      },
      y: {
        ticks: {
          color: "#737c7f",
          font: { family: "Inter", size: 10 },
          callback: yTickFmt || ((v) => v),
        },
        grid: { color: COLORS.grid },
      },
    },
  });

  const showChartEmpty = (canvasId, msg) => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    canvas.width = canvas.parentElement.clientWidth || 300;
    canvas.height = 80;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#737c7f";
    ctx.font = "13px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(msg || "Datos insuficientes para este período", canvas.width / 2, 45);
  };

  const sparseLabels = (arr, max) => {
    if (arr.length <= max) return arr;
    const step = Math.floor(arr.length / max);
    return arr.map((v, i) => (i % step === 0 ? v : ""));
  };

  /* ─── Price chart (Candlestick / Line toggle) ─── */
  const renderPriceChart = (ohlcSeries, bbSeries, pricesSeries) => {
    destroyChart("price");
    if (!ohlcSeries.length && !bbSeries.length && !(pricesSeries && pricesSeries.length)) {
      showChartEmpty("chart-price", "Datos insuficientes para el gráfico de precios");
      $.priceStats.innerHTML = "";
      return;
    }

    const source = ohlcSeries.length ? ohlcSeries : (bbSeries.length ? bbSeries : pricesSeries);
    const labels = source.map((d) => d.date);

    const latestClose = ohlcSeries.length ? ohlcSeries[ohlcSeries.length - 1].close : (bbSeries.length ? bbSeries[bbSeries.length - 1].price : (pricesSeries && pricesSeries.length ? pricesSeries[pricesSeries.length - 1].value : null));
    const firstClose  = ohlcSeries.length ? ohlcSeries[0].close : (bbSeries.length ? bbSeries[0].price : (pricesSeries && pricesSeries.length ? pricesSeries[0].value : null));
    const changePct = (latestClose && firstClose) ? ((latestClose - firstClose) / firstClose * 100) : null;
    const changeCls = changePct !== null ? (changePct >= 0 ? "positive" : "negative") : "";

    $.priceStats.innerHTML =
      `<div class="chart-stat">` +
        `<span class="chart-stat-value">$${escHtml(latestClose !== null ? latestClose.toFixed(2) : "N/A")}</span>` +
        `<span class="chart-stat-label">Último</span>` +
      `</div>` +
      (changePct !== null
        ? `<div class="chart-stat"><span class="chart-stat-value ${changeCls}">` +
          `${escHtml((changePct >= 0 ? "+" : "") + changePct.toFixed(2) + "%")}` +
          `</span><span class="chart-stat-label">Período</span></div>`
        : "");

    if (F.getPriceChartMode() === "candle" && ohlcSeries.length) {
      renderCandlestick(ohlcSeries, labels);
    } else {
      renderPriceLine(ohlcSeries.length ? ohlcSeries : (bbSeries.length ? bbSeries : pricesSeries), labels);
    }
  };

  const renderCandlestick = (ohlcSeries, labels) => {
    const ohlcData = ohlcSeries.map((d) => ({ open: d.open, high: d.high, low: d.low, close: d.close }));
    const bodies = ohlcData.map((d) => [Math.min(d.open, d.close), Math.max(d.open, d.close)]);
    const barColors = ohlcData.map((d) => d.close >= d.open ? COLORS.candleUp : COLORS.candleDn);

    const opts = baseChartOptions((v) => `$${v.toFixed(0)}`, labels);
    opts.plugins.tooltip.callbacks.label = (ctx) => {
      const d = ohlcData[ctx.dataIndex];
      if (!d) return "";
      return [`O: $${d.open.toFixed(2)}`, `H: $${d.high.toFixed(2)}`, `L: $${d.low.toFixed(2)}`, `C: $${d.close.toFixed(2)}`];
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
    $.priceChartSubtitle.textContent = "OHLC Candlestick";
    charts.price._pinFullDates = labels;
  };

  const renderPriceLine = (series, labels) => {
    const prices = series.map((d) =>
      d.close !== undefined ? +d.close.toFixed(2) : (d.price !== undefined ? +d.price.toFixed(2) : (d.value !== undefined && d.value !== null ? +d.value.toFixed(2) : null))
    );

    const opts = baseChartOptions((v) => `$${v}`, labels);
    opts.plugins.tooltip.callbacks.label = (ctx) => `Precio: $${ctx.parsed.y.toFixed(2)}`;

    charts.price = new Chart(document.getElementById("chart-price"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [{
          data: prices,
          borderColor: COLORS.line,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
          backgroundColor: COLORS.fill,
        }],
      },
      options: opts,
    });
    $.priceChartSubtitle.textContent = "Cierre ajustado";
    charts.price._pinFullDates = labels;
  };

  /* ─── Rolling Volatility ─── */
  const renderVolChart = (volSeries, computed) => {
    destroyChart("vol");
    if (!volSeries.length) {
      showChartEmpty("chart-vol", "Datos insuficientes para volatilidad rolling (mín. 22 obs)");
      $.volStats.innerHTML = "";
      return;
    }

    const labels = volSeries.map((d) => d.date);
    const values = volSeries.map((d) => d.value !== null ? +(d.value * 100).toFixed(2) : null);

    const latest = computed.rolling_volatility;
    const latestVal = latest ? `${(latest.latest_sd * 100).toFixed(1)}%` : "N/A";

    $.volStats.innerHTML =
      `<div class="chart-stat">` +
      `<span class="chart-stat-value">${escHtml(latestVal)}</span>` +
      `<span class="chart-stat-label">Actual</span>` +
      `</div>`;

    const opts = baseChartOptions((v) => `${v}%`, labels);
    opts.scales.y.min = 0;
    opts.plugins.tooltip.callbacks.label = (ctx) => `Volatilidad: ${ctx.parsed.y.toFixed(2)}%`;

    charts.vol = new Chart(document.getElementById("chart-vol"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [{
          data: values,
          borderColor: COLORS.line,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: true,
          backgroundColor: COLORS.fill,
        }],
      },
      options: opts,
    });
    charts.vol._pinFullDates = labels;
  };

  /* ─── Bollinger Bands ─── */
  const _renderBollinger = (chartKey, canvasId, statsEl, bbSeries, computed) => {
    destroyChart(chartKey);
    if (!bbSeries.length) {
      showChartEmpty(canvasId, "Datos insuficientes para Bollinger Bands (mín. 20 obs)");
      return;
    }

    const labels = bbSeries.map((d) => d.date);
    const price  = bbSeries.map((d) => d.price !== null ? +d.price.toFixed(2) : null);
    const upper  = bbSeries.map((d) => d.upper !== null ? +d.upper.toFixed(2) : null);
    const mid    = bbSeries.map((d) => d.middle !== null ? +d.middle.toFixed(2) : null);
    const lower  = bbSeries.map((d) => d.lower !== null ? +d.lower.toFixed(2) : null);

    const bb = computed.bollinger;
    if (bb && statsEl) {
      statsEl.innerHTML =
        `<div class="chart-stat"><span class="chart-stat-value negative">${escHtml(fmt(bb.upper, 2))}</span><span class="chart-stat-label">Superior</span></div>` +
        `<div class="chart-stat"><span class="chart-stat-value">${escHtml(fmt(bb.middle, 2))}</span><span class="chart-stat-label">Media</span></div>` +
        `<div class="chart-stat"><span class="chart-stat-value positive">${escHtml(fmt(bb.lower, 2))}</span><span class="chart-stat-label">Inferior</span></div>` +
        `<div class="chart-stat"><span class="chart-stat-value">${escHtml(fmt(bb.percent_b, 2))}</span><span class="chart-stat-label">%B</span></div>`;
    }

    const opts = baseChartOptions((v) => `$${v}`, labels);
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };
    opts.plugins.tooltip.callbacks.label = (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`;

    charts[chartKey] = new Chart(document.getElementById(canvasId), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          { label: "Superior", data: upper, borderColor: COLORS.negative, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 0, fill: false },
          { label: "Media", data: mid, borderColor: COLORS.mid, borderWidth: 1.5, pointRadius: 0, fill: false },
          { label: "Inferior", data: lower, borderColor: COLORS.positive, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 0, fill: "-2", backgroundColor: COLORS.band },
          { label: "Precio", data: price, borderColor: COLORS.line, borderWidth: 2, pointRadius: 0, tension: 0.2, fill: false },
        ],
      },
      options: opts,
    });
    charts[chartKey]._pinFullDates = labels;
  };

  const renderBollingerChart = (bbSeries, computed) => _renderBollinger("bb", "chart-bb", $.bbStats, bbSeries, computed);
  const renderTechBollingerChart = (bbSeries, computed) => _renderBollinger("techBb", "chart-tech-bb", $.techBbStats, bbSeries, computed);

  /* ─── RSI ─── */
  const renderRsiChart = (rsiSeries, computed) => {
    destroyChart("rsi");
    if (!rsiSeries.length) {
      showChartEmpty("chart-rsi", "Datos insuficientes para RSI (mín. 15 obs)");
      $.rsiStats.innerHTML = "";
      return;
    }

    const labels = rsiSeries.map((d) => d.date);
    const values = rsiSeries.map((d) => d.value !== null ? +d.value.toFixed(1) : null);

    const rsi = computed.rsi;
    const rsiVal = rsi ? rsi.latest : null;
    const latestVal = rsiVal !== null ? rsiVal.toFixed(1) : "N/A";
    const latestCls = rsiVal !== null ? (rsiVal > 70 ? "negative" : rsiVal < 30 ? "positive" : "") : "";
    const latestLbl = rsiVal !== null ? (rsiVal > 70 ? "Sobrecompra" : rsiVal < 30 ? "Sobreventa" : "Neutral") : "";

    $.rsiStats.innerHTML =
      `<div class="chart-stat"><span class="chart-stat-value ${latestCls}">${escHtml(latestVal)}</span><span class="chart-stat-label">${escHtml(latestLbl)}</span></div>`;

    const opts = baseChartOptions((v) => v, labels);
    opts.scales.y.min = 0;
    opts.scales.y.max = 100;
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };

    const overbought = values.map(() => 70);
    const oversold   = values.map(() => 30);

    charts.rsi = new Chart(document.getElementById("chart-rsi"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          { label: "Sobrecompra (70)", data: overbought, borderColor: "rgba(186,27,36,0.35)", borderWidth: 1, borderDash: [4, 3], pointRadius: 0, fill: false },
          { label: "Sobreventa (30)", data: oversold, borderColor: "rgba(0,109,74,0.35)", borderWidth: 1, borderDash: [4, 3], pointRadius: 0, fill: false },
          { label: "RSI", data: values, borderColor: COLORS.line, borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false },
        ],
      },
      options: opts,
    });
    charts.rsi._pinFullDates = labels;
  };

  /* ─── MACD ─── */
  const renderMacdChart = (macdSeries) => {
    destroyChart("macd");
    if (!macdSeries.length) {
      showChartEmpty("chart-macd", "Datos insuficientes para MACD (mín. 35 obs)");
      return;
    }

    const labels     = macdSeries.map((d) => d.date);
    const macdLine   = macdSeries.map((d) => d.macd !== null ? +d.macd.toFixed(3) : null);
    const signalLine = macdSeries.map((d) => d.signal !== null ? +d.signal.toFixed(3) : null);
    const histogram  = macdSeries.map((d) => d.histogram !== null ? +d.histogram.toFixed(3) : null);

    const latestMacd   = macdLine[macdLine.length - 1];
    const latestSignal = signalLine[signalLine.length - 1];
    const latestHist   = histogram[histogram.length - 1];

    $.macdStats.innerHTML =
      `<div class="chart-stat"><span class="chart-stat-value">${escHtml(fmt(latestMacd, 3))}</span><span class="chart-stat-label">MACD</span></div>` +
      `<div class="chart-stat"><span class="chart-stat-value">${escHtml(fmt(latestSignal, 3))}</span><span class="chart-stat-label">Signal</span></div>` +
      `<div class="chart-stat"><span class="chart-stat-value ${latestHist >= 0 ? "positive" : "negative"}">${escHtml(fmt(latestHist, 3))}</span><span class="chart-stat-label">Histograma</span></div>`;

    const histColors = histogram.map((v) => v >= 0 ? COLORS.positive : COLORS.negative);

    const opts = baseChartOptions((v) => v, labels);
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };

    charts.macd = new Chart(document.getElementById("chart-macd"), {
      type: "bar",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          { label: "Histograma", data: histogram, backgroundColor: histColors, borderWidth: 0, borderRadius: 1, order: 3 },
          { label: "MACD", data: macdLine, type: "line", borderColor: COLORS.line, borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false, order: 1 },
          { label: "Signal", data: signalLine, type: "line", borderColor: "#f59e0b", borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, order: 2 },
        ],
      },
      options: opts,
    });
    charts.macd._pinFullDates = labels;
  };

  /* ─── Volume ─── */
  const renderVolumeChart = (volumeSeries) => {
    destroyChart("volume");
    if (!volumeSeries.length) {
      $.volumeStats.innerHTML = '<span class="chart-stat-label">Sin datos de volumen</span>';
      return;
    }

    const labels = volumeSeries.map((d) => d.date);
    const values = volumeSeries.map((d) => d.value !== null ? +d.value : null);

    const smaWindow = 20;
    const sma = values.map((_, i) => {
      if (i < smaWindow - 1) return null;
      let sum = 0;
      for (let j = i - smaWindow + 1; j <= i; j++) sum += (values[j] || 0);
      return sum / smaWindow;
    });

    const validVals = values.filter((v) => v !== null);
    const avgVol = validVals.length ? validVals.reduce((a, b) => a + b, 0) / validVals.length : 0;
    const latestVol = validVals.length ? validVals[validVals.length - 1] : 0;

    $.volumeStats.innerHTML =
      `<div class="chart-stat">` +
        `<span class="chart-stat-value">${escHtml(fmtCompact(latestVol))}</span>` +
        `<span class="chart-stat-label">Último</span>` +
      `</div>` +
      `<div class="chart-stat">` +
        `<span class="chart-stat-value">${escHtml(fmtCompact(avgVol))}</span>` +
        `<span class="chart-stat-label">Promedio</span>` +
      `</div>`;

    const opts = baseChartOptions((v) => fmtCompact(v), labels);
    opts.scales.y.min = 0;
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };
    opts.plugins.tooltip.callbacks.label = (ctx) => `${ctx.dataset.label}: ${fmtCompact(ctx.parsed.y)}`;

    charts.volume = new Chart(document.getElementById("chart-volume"), {
      type: "bar",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [
          { label: "Volumen", data: values, backgroundColor: COLORS.volume, borderWidth: 0, borderRadius: 1, order: 2 },
          { label: "SMA 20d", data: sma, type: "line", borderColor: COLORS.volumeAvg, borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false, order: 1 },
        ],
      },
      options: opts,
    });
    charts.volume._pinFullDates = labels;
  };

  /* ─── GARCH Conditional Volatility ─── */
  const REGIME_COLORS = {
    low_vol:  "#006d4a",
    mid_vol:  "#f59e0b",
    high_vol: "#ba1b24",
  };

  const renderGarchVolChart = (garchVol) => {
    destroyChart("garchVol");
    if (!garchVol.length) {
      showChartEmpty("chart-garch-vol", "Datos insuficientes para GARCH");
      $.garchVolStats.innerHTML = "";
      return;
    }

    const labels = garchVol.map((d) => d.date);
    const values = garchVol.map((d) => d.value !== null ? +(d.value * 100).toFixed(3) : null);

    const latest = values[values.length - 1];
    $.garchVolStats.innerHTML =
      `<div class="chart-stat">` +
        `<span class="chart-stat-value">${escHtml(latest !== null ? `${latest.toFixed(2)}%` : "N/A")}</span>` +
        `<span class="chart-stat-label">Actual</span>` +
      `</div>`;

    const opts = baseChartOptions((v) => `${v.toFixed(1)}%`, labels);
    opts.scales.y.min = 0;
    opts.plugins.tooltip.callbacks.label = (ctx) => `Vol condicional: ${ctx.parsed.y.toFixed(3)}%`;

    charts.garchVol = new Chart(document.getElementById("chart-garch-vol"), {
      type: "line",
      data: {
        labels: sparseLabels(labels, 10),
        datasets: [{
          data: values,
          borderColor: COLORS.line,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: true,
          backgroundColor: COLORS.fill,
        }],
      },
      options: opts,
    });
  };

  /* ─── GARCH Forecast Cone ─── */
  const renderGarchForecastChart = (forecast, confidence) => {
    destroyChart("garchForecast");
    if (!forecast || !forecast.length) {
      showChartEmpty("chart-garch-forecast", "Pronóstico no disponible");
      $.garchForecastStats.innerHTML = "";
      return;
    }

    const labels = forecast.map((d) => `Día ${d.day}`);
    const point  = forecast.map((d) => +(d.volatility * 100).toFixed(3));
    const upper  = forecast.map((d) => +(d.upper * 100).toFixed(3));
    const lower  = forecast.map((d) => +(d.lower * 100).toFixed(3));

    const confPct = confidence ? Math.round(confidence * 100) : 95;
    $.garchForecastSubtitle.textContent = `GARCH(1,1) · ${forecast.length} días · IC ${confPct}%`;

    $.garchForecastStats.innerHTML =
      `<div class="chart-stat">` +
        `<span class="chart-stat-value">${escHtml(`${point[0].toFixed(2)}%`)}</span>` +
        `<span class="chart-stat-label">Día 1</span>` +
      `</div>` +
      `<div class="chart-stat">` +
        `<span class="chart-stat-value">${escHtml(`${point[point.length - 1].toFixed(2)}%`)}</span>` +
        `<span class="chart-stat-label">Día ${forecast.length}</span>` +
      `</div>`;

    const opts = baseChartOptions((v) => `${v.toFixed(2)}%`);
    opts.scales.y.min = 0;
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };
    opts.plugins.tooltip.callbacks.label = (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}%`;

    charts.garchForecast = new Chart(document.getElementById("chart-garch-forecast"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Superior", data: upper, borderColor: COLORS.negative, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 2, fill: false },
          { label: "Pronóstico", data: point, borderColor: COLORS.line, borderWidth: 2.5, pointRadius: 3, pointBackgroundColor: COLORS.line, fill: false },
          { label: "Inferior", data: lower, borderColor: COLORS.positive, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 2, fill: "-2", backgroundColor: "rgba(26,86,219,0.08)" },
        ],
      },
      options: opts,
    });
  };

  /* ─── HMM Regime Timeline Bar ─── */
  const renderHmmRegimesChart = (hmmStates) => {
    destroyChart("hmmRegimes");
    if (!hmmStates.length) {
      showChartEmpty("chart-hmm-regimes", "Datos insuficientes para HMM");
      $.hmmStats.innerHTML = "";
      $.hmmLegend.innerHTML = "";
      return;
    }

    const labels = hmmStates.map((d) => d.date);
    const stateLabels = hmmStates.map((d) => d.label);
    const data = hmmStates.map(() => 1);
    const bgColors = hmmStates.map((d) => REGIME_COLORS[d.label] || COLORS.neutral);

    const counts = {};
    stateLabels.forEach((l) => { counts[l] = (counts[l] || 0) + 1; });
    const total = stateLabels.length;

    const legendLabels = { low_vol: "Baja vol", mid_vol: "Vol moderada", high_vol: "Alta vol" };

    let statHtml = "";
    Object.keys(REGIME_COLORS).forEach((key) => {
      if (counts[key]) {
        const pct = (counts[key] / total * 100).toFixed(0);
        statHtml +=
          `<div class="chart-stat">` +
            `<span class="chart-stat-value" style="color:${REGIME_COLORS[key]}">${pct}%</span>` +
            `<span class="chart-stat-label">${escHtml(legendLabels[key] || key)}</span>` +
          `</div>`;
      }
    });
    $.hmmStats.innerHTML = statHtml;

    let legendHtml = "";
    Object.keys(REGIME_COLORS).forEach((key) => {
      if (counts[key]) {
        legendHtml +=
          `<span class="hmm-legend-item">` +
            `<span class="hmm-legend-dot" style="background:${REGIME_COLORS[key]}"></span>` +
            `${escHtml(legendLabels[key] || key)}` +
          `</span>`;
      }
    });
    $.hmmLegend.innerHTML = legendHtml;

    const opts = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 200 },
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
            title: (items) => items.length ? labels[items[0].dataIndex] : "",
            label: (ctx) => {
              const l = stateLabels[ctx.dataIndex];
              const names = { low_vol: "Baja volatilidad", mid_vol: "Volatilidad moderada", high_vol: "Alta volatilidad" };
              return names[l] || l;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#737c7f", font: { family: "Inter", size: 10 }, maxTicksLimit: 8, maxRotation: 0 },
          grid: { display: false },
        },
        y: { display: false, min: 0, max: 1 },
      },
    };

    charts.hmmRegimes = new Chart(document.getElementById("chart-hmm-regimes"), {
      type: "bar",
      data: {
        labels: sparseLabels(labels, 12),
        datasets: [{
          data,
          backgroundColor: bgColors,
          borderWidth: 0,
          barPercentage: 1.0,
          categoryPercentage: 1.0,
        }],
      },
      options: opts,
    });
  };

  /* ─── HMM Gaussian Distributions ─── */
  const renderHmmDistributionsChart = (distributions) => {
    destroyChart("hmmDist");
    if (!distributions || !distributions.length) {
      showChartEmpty("chart-hmm-dist", "Distribuciones no disponibles");
      return;
    }

    const xVals = distributions[0].x;
    const labels = xVals.map((v) => (v * 100).toFixed(2));

    const datasets = distributions.map((d) => {
      const c = REGIME_COLORS[d.label] || COLORS.line;
      let bg = c;
      if (c.charAt(0) === "#") {
        const r = parseInt(c.slice(1, 3), 16);
        const g = parseInt(c.slice(3, 5), 16);
        const b = parseInt(c.slice(5, 7), 16);
        bg = `rgba(${r},${g},${b},0.12)`;
      }
      return {
        label: d.label_es,
        data: d.pdf,
        borderColor: c,
        backgroundColor: bg,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.4,
        fill: true,
      };
    });

    const opts = baseChartOptions(null, labels);
    opts.scales.x.title = { display: true, text: "Retorno diario (%)", color: "#737c7f", font: { family: "Inter", size: 11 } };
    opts.scales.y.title = { display: true, text: "Densidad", color: "#737c7f", font: { family: "Inter", size: 11 } };
    opts.scales.y.min = 0;
    opts.scales.x.ticks.maxTicksLimit = 10;
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };
    opts.plugins.tooltip.callbacks.title = (items) => items.length ? `Retorno: ${items[0].label}%` : "";
    opts.plugins.tooltip.callbacks.label = (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}`;

    charts.hmmDist = new Chart(document.getElementById("chart-hmm-dist"), {
      type: "line",
      data: { labels, datasets },
      options: opts,
    });
  };

  /* ─── Pin group initialization ─── */
  const initPinGroup = (groupName) => {
    const group = pinGroups[groupName];
    if (!group) return;
    for (const key of group.chartKeys) {
      attachPinGroup(key, groupName);
      setupPinListeners(key, groupName);
      // Store full date labels for pin display
      if (charts[key] && charts[key]._pinFullDates === undefined) {
        charts[key]._pinFullDates = charts[key].data.labels;
      }
    }
  };

  /* ─── Expose ─── */
  F.destroyChart = destroyChart;
  F.destroyAllCharts = destroyAllCharts;
  F.renderPriceChart = renderPriceChart;
  F.renderVolChart = renderVolChart;
  F.renderBollingerChart = renderBollingerChart;
  F.renderTechBollingerChart = renderTechBollingerChart;
  F.renderRsiChart = renderRsiChart;
  F.renderMacdChart = renderMacdChart;
  F.renderVolumeChart = renderVolumeChart;
  F.renderGarchVolChart = renderGarchVolChart;
  F.renderGarchForecastChart = renderGarchForecastChart;
  F.renderHmmRegimesChart = renderHmmRegimesChart;
  F.renderHmmDistributionsChart = renderHmmDistributionsChart;
  F.REGIME_COLORS = REGIME_COLORS;
  F.initPinGroup = initPinGroup;
  F.clearPins = clearPins;
  F.pinGroups = pinGroups;
})();
