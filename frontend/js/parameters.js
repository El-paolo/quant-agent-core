/* ============================================================
   FINA — Advanced Parameters Management
   ============================================================ */

(() => {
  "use strict";

  const F = window.FINA;
  const state = F.state;
  const $ = F.$;
  const show = F.show;
  const hide = F.hide;

  const PARAMS_STORAGE_KEY = "FINA_advanced_params";

  /* ─── Load parameters from localStorage ─── */
  const loadParameters = () => {
    try {
      const saved = localStorage.getItem(PARAMS_STORAGE_KEY);
      if (saved) {
        const data = JSON.parse(saved);
        state.params = { ...state.params, ...data };
      }
    } catch (e) {
      console.error("Error loading parameters:", e);
    }
  };

  /* ─── Save parameters to localStorage ─── */
  const saveParameters = () => {
    try {
      localStorage.setItem(PARAMS_STORAGE_KEY, JSON.stringify(state.params));
    } catch (e) {
      console.error("Error saving parameters:", e);
    }
  };

  /* ─── Setup advanced parameters section ─── */
  const setupAdvancedParams = () => {
    const toggleBtn = document.getElementById("params-adv-toggle");
    const advBody = document.getElementById("params-adv-body");
    const rfInput = document.getElementById("param-rf-rate");
    const marInput = document.getElementById("param-mar");
    const volInput = document.getElementById("param-vol-window");
    const resetBtn = document.getElementById("param-reset-btn");

    if (!toggleBtn || !advBody) return;

    // Load saved values into inputs
    loadParameters();
    rfInput.value = state.params.rf_rate;
    marInput.value = state.params.mar;
    volInput.value = state.params.vol_window;

    // Toggle collapse/expand
    toggleBtn.addEventListener("click", () => {
      const isOpen = !advBody.classList.contains("hidden");
      if (isOpen) {
        hide(advBody);
        toggleBtn.classList.remove("open");
        state.paramsAdvOpen = false;
      } else {
        show(advBody);
        toggleBtn.classList.add("open");
        state.paramsAdvOpen = true;
      }
    });

    // Handle input changes
    rfInput.addEventListener("change", (e) => {
      state.params.rf_rate = parseFloat(e.target.value) || 0;
      saveParameters();
    });

    marInput.addEventListener("change", (e) => {
      state.params.mar = parseFloat(e.target.value) || 0;
      saveParameters();
    });

    volInput.addEventListener("change", (e) => {
      state.params.vol_window = Math.max(5, Math.min(252, parseInt(e.target.value) || 21));
      e.target.value = state.params.vol_window;
      saveParameters();
    });

    // Reset to defaults
    resetBtn.addEventListener("click", () => {
      if (confirm("¿Restaurar parámetros por defecto?")) {
        state.params = {
          rf_rate: 5.0,
          mar: 0.0,
          vol_window: 21,
        };
        rfInput.value = state.params.rf_rate;
        marInput.value = state.params.mar;
        volInput.value = state.params.vol_window;
        saveParameters();
      }
    });

    // If paramsAdvOpen was true from previous session, open it
    if (state.paramsAdvOpen) {
      show(advBody);
      toggleBtn.classList.add("open");
    }
  };

  /* ─── Initialize ─── */
  const init = () => {
    loadParameters();
    setupAdvancedParams();
  };

  /* ─── Expose ─── */
  F.getParam = (key) => state.params[key];
  F.setParam = (key, value) => {
    state.params[key] = value;
    saveParameters();
  };

  init();
})();
