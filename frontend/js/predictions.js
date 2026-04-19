/* ============================================================
   FINA — Predictions Panel
   ============================================================ */

(() => {
  "use strict";

  const F = window.FINA;
  const state = F.state;
  const $ = F.$;
  const show = F.show;
  const hide = F.hide;
  const fmt = F.fmt;

  const STORAGE_KEY = "FINA_predictions";

  const METRICS_CONFIG = {
    target_date: { label: "Fecha destino", type: "date" },
    predicted_price: { label: "Precio predicho", type: "number" },
    real_price: { label: "Precio real", type: "number" },
    confidence: { label: "Confianza (%)", type: "number" },
    mae: { label: "MAE", type: "number" },
    accuracy: { label: "Precisión (%)", type: "number" },
    status: { label: "Estado", type: "text" },
    created_at: { label: "Fecha creación", type: "date" },
    error_pct: { label: "Error (%)", type: "number" },
  };

  /* ─── Load predictions from localStorage ─── */
  const loadPredictions = () => {
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      state.predictions = data ? JSON.parse(data) : [];
    } catch (e) {
      console.error("Error loading predictions:", e);
      state.predictions = [];
    }
  };

  /* ─── Save predictions to localStorage ─── */
  const savePredictions = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.predictions));
    } catch (e) {
      console.error("Error saving predictions:", e);
    }
  };

  /* ─── Validate prediction ─── */
  const validatePrediction = (ticker, targetDate, predictedPrice, confidence) => {
    if (!ticker || !targetDate || !predictedPrice || confidence === null || confidence === "") {
      return "Todos los campos son requeridos";
    }
    if (isNaN(predictedPrice) || predictedPrice <= 0) {
      return "El precio debe ser un número positivo";
    }
    if (isNaN(confidence) || confidence < 0 || confidence > 100) {
      return "La confianza debe estar entre 0 y 100";
    }
    return null;
  };

  /* ─── Add prediction ─── */
  const addPrediction = (ticker, targetDate, predictedPrice, confidence) => {
    const error = validatePrediction(ticker, targetDate, predictedPrice, confidence);
    if (error) return { success: false, error };

    const prediction = {
      id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      ticker: ticker.toUpperCase().trim(),
      targetDate,
      predictedPrice: parseFloat(predictedPrice),
      confidence: parseFloat(confidence),
      realPrice: null,
      status: "pending",
      createdAt: new Date().toISOString().split("T")[0],
      mae: null,
      accuracy: null,
      errorPct: null,
    };

    state.predictions.push(prediction);
    savePredictions();
    return { success: true, prediction };
  };

  /* ─── Delete prediction ─── */
  const deletePrediction = (id) => {
    state.predictions = state.predictions.filter((p) => p.id !== id);
    savePredictions();
  };

  /* ─── Calculate metrics ─── */
  const calculateMetrics = (prediction, realPrice) => {
    if (!realPrice) return { mae: null, accuracy: null, errorPct: null };

    const mae = Math.abs(prediction.predictedPrice - realPrice);
    const errorPct = (mae / realPrice) * 100;
    const accuracy = Math.max(0, 100 - errorPct);

    return { mae: fmt(mae, 2), accuracy: fmt(accuracy, 1), errorPct: fmt(errorPct, 1) };
  };

  /* ─── Get status badge HTML ─── */
  const getStatusBadge = (status) => {
    const badges = {
      pending: '<span class="status-badge status-pending">🕐 Pendiente</span>',
      hit: '<span class="status-badge status-hit">✓ Correcto</span>',
      miss: '<span class="status-badge status-miss">✗ Incorrecto</span>',
    };
    return badges[status] || '<span class="status-badge">—</span>';
  };

  /* ─── Render predictions table ─── */
  const renderPredictionsTable = () => {
    const visible = state.predictionsVisibleMetrics;

    // Build header
    $.predTableHeader.innerHTML = visible
      .map((metric) => `<th>${METRICS_CONFIG[metric]?.label || metric}</th>`)
      .concat(['<th style="width: 40px;"></th>'])
      .join("");

    // Build rows
    $.predTableBody.innerHTML = state.predictions
      .map((pred) => {
        const cells = visible.map((metric) => {
          let value = pred[metric];
          if (metric === "status") return `<td>${getStatusBadge(value)}</td>`;
          if (metric === "predicted_price" || metric === "real_price" || metric === "mae") {
            return `<td>$${fmt(value, 2)}</td>`;
          }
          if (metric === "accuracy" || metric === "error_pct" || metric === "confidence") {
            return `<td>${fmt(value, 1)}%</td>`;
          }
          return `<td>${value || "—"}</td>`;
        });

        const deleteBtn = `
          <td class="pred-action">
            <button class="pred-delete-btn" data-id="${pred.id}" title="Eliminar">×</button>
          </td>
        `;

        return `<tr>${cells.join("")}${deleteBtn}</tr>`;
      })
      .join("");

    // Update count and empty state
    $.predTableCount.textContent = `Predicciones (${state.predictions.length})`;
    if (state.predictions.length === 0) {
      hide($.predTableBody.parentElement);
      show($.predEmpty);
    } else {
      show($.predTableBody.parentElement);
      hide($.predEmpty);
    }
  };

  /* ─── Update visible columns ─── */
  const updateVisibleColumns = () => {
    const checks = $.metricsSelectBody.querySelectorAll('input[type="checkbox"]');
    state.predictionsVisibleMetrics = [];
    checks.forEach((cb) => {
      if (cb.checked) state.predictionsVisibleMetrics.push(cb.value);
    });
    renderPredictionsTable();
  };

  /* ─── Export to CSV ─── */
  const exportCSV = () => {
    if (state.predictions.length === 0) {
      alert("No hay predicciones para exportar");
      return;
    }

    const headers = ["ID", "Ticker", "Fecha destino", "Precio predicho", "Precio real", "Confianza (%)", "MAE", "Precisión (%)", "Estado"];
    const rows = state.predictions.map((pred) => [
      pred.id,
      pred.ticker,
      pred.targetDate,
      pred.predictedPrice,
      pred.realPrice || "—",
      pred.confidence,
      pred.mae || "—",
      pred.accuracy || "—",
      pred.status,
    ]);

    const csv = [headers, ...rows].map((row) => row.map((cell) => `"${cell}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `FINA_predictions_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  /* ─── Setup form handler ─── */
  const setupFormHandler = () => {
    $.predForm.addEventListener("submit", (e) => {
      e.preventDefault();

      const result = addPrediction(
        $.predTicker.value,
        $.predTargetDate.value,
        $.predPrice.value,
        $.predConfidence.value
      );

      if (!result.success) {
        alert(result.error);
        return;
      }

      // Clear form
      $.predForm.reset();
      $.predConfidence.value = "50";
      renderPredictionsTable();
    });
  };

  /* ─── Setup metrics selector ─── */
  const setupMetricsSelector = () => {
    $.metricsSelectToggle.addEventListener("click", () => {
      const isOpen = !$.metricsSelectBody.classList.contains("hidden");
      if (isOpen) hide($.metricsSelectBody);
      else show($.metricsSelectBody);

      // Toggle chevron
      $.metricsSelectToggle.classList.toggle("open");
    });

    $.metricsSelectBody.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", updateVisibleColumns);
    });
  };

  /* ─── Setup delete handlers ─── */
  const setupDeleteHandlers = () => {
    $.predTableBody.addEventListener("click", (e) => {
      const btn = e.target.closest(".pred-delete-btn");
      if (btn) {
        const id = btn.dataset.id;
        if (confirm("¿Eliminar predicción?")) {
          deletePrediction(id);
          renderPredictionsTable();
        }
      }
    });
  };

  /* ─── Setup export handler ─── */
  const setupExportHandler = () => {
    $.predExportBtn.addEventListener("click", exportCSV);
  };

  /* ─── Load panel ─── */
  const loadPredictionsPanel = () => {
    loadPredictions();
    renderPredictionsTable();
    show($.predictionsContent);
  };

  /* ─── Initialize ─── */
  const init = () => {
    setupFormHandler();
    setupMetricsSelector();
    setupDeleteHandlers();
    setupExportHandler();
  };

  /* ─── Expose ─── */
  F.loadPredictionsPanel = loadPredictionsPanel;
  F.addPrediction = addPrediction;

  init();
})();
