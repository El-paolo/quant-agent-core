/* ============================================================
   FINA — Q&A Assistant (Drawer)
   ============================================================ */

(function () {
  "use strict";

  var F = window.FINA;
  var state = F.state;
  var $ = F.$;
  var escHtml = F.escHtml;

  /* ─── Toggle drawer ─── */
  function openDrawer() {
    state.chatOpen = true;
    $.assistantDrawer.classList.remove("hidden");
    $.assistantFab.classList.add("hidden");
    $.assistantInput.focus();
  }

  function closeDrawer() {
    state.chatOpen = false;
    $.assistantDrawer.classList.add("hidden");
    $.assistantFab.classList.remove("hidden");
  }

  $.assistantFab.addEventListener("click", openDrawer);
  $.assistantClose.addEventListener("click", closeDrawer);

  /* ─── Gather context from current state ─── */
  function gatherContext() {
    var ctx = {};

    if (state.ticker) ctx.ticker = state.ticker;
    if (state.period) ctx.period = state.period;

    if (state.analysisResult && state.analysisResult.data) {
      var c = state.analysisResult.data.computed || {};
      if (c.sharpe) ctx.sharpe = F.fmt(c.sharpe.sharpe_ratio);
      if (c.sortino) ctx.sortino = F.fmt(c.sortino.sortino_ratio);
      if (c.beta) ctx.beta = F.fmt(c.beta.beta);
      if (c.rsi) ctx.rsi = F.fmt(c.rsi.latest, 1);
      if (c.rolling_volatility) ctx.volatility = F.fmtPct(c.rolling_volatility.latest_sd);
      if (c.returns) ctx.annualized_return = F.fmtSign(c.returns.mean * 252);
    }

    if (state.modelsResult) {
      var m = state.modelsResult;
      if (m.garch && m.garch.diagnostics) {
        ctx.garch_persistence = F.fmt(m.garch.diagnostics.persistence, 4);
      }
      if (m.hmm && m.hmm.current_regime) {
        ctx.hmm_regime = m.hmm.current_regime.label_es;
      }
      if (m.arima && m.arima.diagnostics) {
        ctx.arima_order = m.arima.diagnostics.order;
      }
    }

    if (state.comparisonResult && state.comparisonResult.verdict) {
      ctx.comparison_verdict = state.comparisonResult.verdict.summary_es;
    }

    return Object.keys(ctx).length > 0 ? ctx : null;
  }

  /* ─── Render a message bubble ─── */
  function appendMessage(role, text) {
    var div = document.createElement("div");
    div.className = "assistant-msg assistant-msg--" + role;
    div.textContent = text;
    $.assistantMessages.appendChild(div);
    $.assistantMessages.scrollTop = $.assistantMessages.scrollHeight;
    return div;
  }

  /* ─── Send question ─── */
  function sendQuestion(question) {
    appendMessage("user", question);

    var loadingEl = appendMessage("assistant", "...");
    loadingEl.classList.add("assistant-msg--loading");

    $.assistantInput.disabled = true;
    $.assistantSend.disabled = true;

    var ctx = gatherContext();
    var body = { question: question };
    if (ctx && ctx.ticker) body.ticker = ctx.ticker;
    if (ctx) body.context = ctx;

    fetch("/agent/ask/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Error " + r.status); });
        return r.json();
      })
      .then(function (data) {
        loadingEl.textContent = data.answer;
        loadingEl.classList.remove("assistant-msg--loading");
      })
      .catch(function (err) {
        loadingEl.textContent = "Error: " + err.message;
        loadingEl.classList.remove("assistant-msg--loading");
        loadingEl.classList.add("assistant-msg--error");
      })
      .finally(function () {
        $.assistantInput.disabled = false;
        $.assistantSend.disabled = false;
        $.assistantInput.focus();
      });
  }

  /* ─── Form submit ─── */
  $.assistantForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var question = $.assistantInput.value.trim();
    if (!question) return;
    $.assistantInput.value = "";
    sendQuestion(question);
  });
})();
