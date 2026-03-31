/* ============================================================
   FINA — Chart Rendering (Chart.js)
   ============================================================ */

(function () {
  "use strict";

  var F = window.FINA;
  var charts = F.charts;
  var COLORS = F.CHART_COLORS;
  var escHtml = F.escHtml;
  var fmt = F.fmt;
  var fmtPct = F.fmtPct;
  var fmtSign = F.fmtSign;
  var fmtCompact = F.fmtCompact;
  var sentiment = F.sentiment;
  var $ = F.$;

  /* ─── Lifecycle ─── */
  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  }

  function destroyAllCharts() {
    Object.keys(charts).forEach(destroyChart);
  }

  /* ─── Auto-scale Y after zoom/pan ─── */
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
    var padding = (yMax - yMin) * 0.05 || 1;
    yScale.options.min = yMin - padding;
    yScale.options.max = yMax + padding;
    chart.update("none");
  }

  /* ─── Shared chart config ─── */
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
          grid: { color: COLORS.grid },
        },
        y: {
          ticks: {
            color: "#737c7f",
            font: { family: "Inter", size: 10 },
            callback: yTickFmt || function (v) { return v; },
          },
          grid: { color: COLORS.grid },
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
      $.priceStats.innerHTML = "";
      return;
    }

    var source = ohlcSeries.length ? ohlcSeries : (bbSeries.length ? bbSeries : pricesSeries);
    var labels = source.map(function (d) { return d.date; });

    var latestClose = ohlcSeries.length ? ohlcSeries[ohlcSeries.length - 1].close : (bbSeries.length ? bbSeries[bbSeries.length - 1].price : (pricesSeries && pricesSeries.length ? pricesSeries[pricesSeries.length - 1].value : null));
    var firstClose  = ohlcSeries.length ? ohlcSeries[0].close : (bbSeries.length ? bbSeries[0].price : (pricesSeries && pricesSeries.length ? pricesSeries[0].value : null));
    var changePct = (latestClose && firstClose) ? ((latestClose - firstClose) / firstClose * 100) : null;
    var changeCls = changePct !== null ? (changePct >= 0 ? "positive" : "negative") : "";

    $.priceStats.innerHTML =
      '<div class="chart-stat">' +
        '<span class="chart-stat-value">$' + escHtml(latestClose !== null ? latestClose.toFixed(2) : "N/A") + '</span>' +
        '<span class="chart-stat-label">Último</span>' +
      '</div>' +
      (changePct !== null ?
        '<div class="chart-stat"><span class="chart-stat-value ' + changeCls + '">' +
          escHtml((changePct >= 0 ? "+" : "") + changePct.toFixed(2) + "%") +
        '</span><span class="chart-stat-label">Período</span></div>' : "");

    if (F.getPriceChartMode() === "candle" && ohlcSeries.length) {
      renderCandlestick(ohlcSeries, labels);
    } else {
      renderPriceLine(ohlcSeries.length ? ohlcSeries : (bbSeries.length ? bbSeries : pricesSeries), labels);
    }
  }

  function renderCandlestick(ohlcSeries, labels) {
    var ohlcData = ohlcSeries.map(function (d) {
      return { open: d.open, high: d.high, low: d.low, close: d.close };
    });
    var bodies = ohlcData.map(function (d) {
      return [Math.min(d.open, d.close), Math.max(d.open, d.close)];
    });
    var barColors = ohlcData.map(function (d) {
      return d.close >= d.open ? COLORS.candleUp : COLORS.candleDn;
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
    $.priceChartSubtitle.textContent = "OHLC Candlestick";
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
  }

  /* ─── Rolling Volatility ─── */
  function renderVolChart(volSeries, computed) {
    destroyChart("vol");
    if (!volSeries.length) {
      showChartEmpty("chart-vol", "Datos insuficientes para volatilidad rolling (mín. 22 obs)");
      $.volStats.innerHTML = "";
      return;
    }

    var labels = volSeries.map(function (d) { return d.date; });
    var values = volSeries.map(function (d) { return d.value !== null ? +(d.value * 100).toFixed(2) : null; });

    var latest = computed.rolling_volatility;
    var latestVal = latest ? (latest.latest_sd * 100).toFixed(1) + "%" : "N/A";

    $.volStats.innerHTML =
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
  }

  /* ─── Bollinger Bands ─── */
  function _renderBollinger(chartKey, canvasId, statsEl, bbSeries, computed) {
    destroyChart(chartKey);
    if (!bbSeries.length) {
      showChartEmpty(canvasId, "Datos insuficientes para Bollinger Bands (mín. 20 obs)");
      return;
    }

    var labels = bbSeries.map(function (d) { return d.date; });
    var price  = bbSeries.map(function (d) { return d.price !== null ? +d.price.toFixed(2) : null; });
    var upper  = bbSeries.map(function (d) { return d.upper !== null ? +d.upper.toFixed(2) : null; });
    var mid    = bbSeries.map(function (d) { return d.middle !== null ? +d.middle.toFixed(2) : null; });
    var lower  = bbSeries.map(function (d) { return d.lower !== null ? +d.lower.toFixed(2) : null; });

    var bb = computed.bollinger;
    if (bb && statsEl) {
      statsEl.innerHTML =
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
  }

  function renderBollingerChart(bbSeries, computed) {
    _renderBollinger("bb", "chart-bb", $.bbStats, bbSeries, computed);
  }

  function renderTechBollingerChart(bbSeries, computed) {
    _renderBollinger("techBb", "chart-tech-bb", $.techBbStats, bbSeries, computed);
  }

  /* ─── RSI ─── */
  function renderRsiChart(rsiSeries, computed) {
    destroyChart("rsi");
    if (!rsiSeries.length) {
      showChartEmpty("chart-rsi", "Datos insuficientes para RSI (mín. 15 obs)");
      $.rsiStats.innerHTML = "";
      return;
    }

    var labels = rsiSeries.map(function (d) { return d.date; });
    var values = rsiSeries.map(function (d) { return d.value !== null ? +d.value.toFixed(1) : null; });

    var rsi = computed.rsi;
    var rsiVal = rsi ? rsi.latest : null;
    var latestVal = rsiVal !== null ? rsiVal.toFixed(1) : "N/A";
    var latestCls = rsiVal !== null ? (rsiVal > 70 ? "negative" : rsiVal < 30 ? "positive" : "") : "";
    var latestLbl = rsiVal !== null ? (rsiVal > 70 ? "Sobrecompra" : rsiVal < 30 ? "Sobreventa" : "Neutral") : "";

    $.rsiStats.innerHTML =
      '<div class="chart-stat"><span class="chart-stat-value ' + latestCls + '">' + escHtml(latestVal) + '</span><span class="chart-stat-label">' + escHtml(latestLbl) + '</span></div>';

    var opts = baseChartOptions(function (v) { return v; }, labels);
    opts.scales.y.min = 0;
    opts.scales.y.max = 100;
    opts.plugins.legend = {
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };

    var overbought = values.map(function () { return 70; });
    var oversold   = values.map(function () { return 30; });

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
  }

  /* ─── MACD ─── */
  function renderMacdChart(macdSeries) {
    destroyChart("macd");
    if (!macdSeries.length) {
      showChartEmpty("chart-macd", "Datos insuficientes para MACD (mín. 35 obs)");
      return;
    }

    var labels     = macdSeries.map(function (d) { return d.date; });
    var macdLine   = macdSeries.map(function (d) { return d.macd !== null ? +d.macd.toFixed(3) : null; });
    var signalLine = macdSeries.map(function (d) { return d.signal !== null ? +d.signal.toFixed(3) : null; });
    var histogram  = macdSeries.map(function (d) { return d.histogram !== null ? +d.histogram.toFixed(3) : null; });

    var latestMacd   = macdLine[macdLine.length - 1];
    var latestSignal = signalLine[signalLine.length - 1];
    var latestHist   = histogram[histogram.length - 1];

    $.macdStats.innerHTML =
      '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(latestMacd, 3)) + '</span><span class="chart-stat-label">MACD</span></div>' +
      '<div class="chart-stat"><span class="chart-stat-value">' + escHtml(fmt(latestSignal, 3)) + '</span><span class="chart-stat-label">Signal</span></div>' +
      '<div class="chart-stat"><span class="chart-stat-value ' + (latestHist >= 0 ? "positive" : "negative") + '">' + escHtml(fmt(latestHist, 3)) + '</span><span class="chart-stat-label">Histograma</span></div>';

    var histColors = histogram.map(function (v) {
      return v >= 0 ? COLORS.positive : COLORS.negative;
    });

    var opts = baseChartOptions(function (v) { return v; }, labels);
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
  }

  /* ─── Volume ─── */
  function renderVolumeChart(volumeSeries) {
    destroyChart("volume");
    if (!volumeSeries.length) {
      $.volumeStats.innerHTML = '<span class="chart-stat-label">Sin datos de volumen</span>';
      return;
    }

    var labels = volumeSeries.map(function (d) { return d.date; });
    var values = volumeSeries.map(function (d) { return d.value !== null ? +d.value : null; });

    var smaWindow = 20;
    var sma = values.map(function (_, i) {
      if (i < smaWindow - 1) return null;
      var sum = 0;
      for (var j = i - smaWindow + 1; j <= i; j++) sum += (values[j] || 0);
      return sum / smaWindow;
    });

    var validVals = values.filter(function (v) { return v !== null; });
    var avgVol = validVals.length ? validVals.reduce(function (a, b) { return a + b; }, 0) / validVals.length : 0;
    var latestVol = validVals.length ? validVals[validVals.length - 1] : 0;

    $.volumeStats.innerHTML =
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
      display: true, position: "bottom",
      labels: { color: "#586064", font: { family: "Inter", size: 11 }, boxWidth: 12, boxHeight: 2, padding: 16 },
    };
    opts.plugins.tooltip.callbacks.label = function (ctx) {
      return ctx.dataset.label + ": " + fmtCompact(ctx.parsed.y);
    };

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
  }

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
})();
