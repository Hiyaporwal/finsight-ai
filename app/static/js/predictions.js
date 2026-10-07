(function () {
  const box = document.getElementById("predBox");
  if (!box) return;
  const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
  const horizonSel = document.getElementById("predHorizon");
  const modelSel = document.getElementById("predModel");
  let symbol = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function show(d) {
    box.replaceChildren();
    const up = d.predicted_change_pct >= 0;
    box.appendChild(el("div", "text-muted", `${d.symbol} · ${d.model} · ${d.horizon_sessions} session(s) ahead`));
    box.appendChild(el("div", "h5 mb-0", inr.format(d.predicted_price)));
    box.appendChild(el("div", up ? "up" : "down",
      `${up ? "+" : ""}${d.predicted_change_pct.toFixed(2)}% vs latest ${inr.format(d.latest_close)} (${d.latest_date})`));
    box.appendChild(el("div", "mt-2",
      `Test MAPE ${d.metrics.mape.toFixed(2)}% vs naive baseline ${d.baseline.mape.toFixed(2)}%`));
    box.appendChild(el("div", d.beats_baseline ? "text-success" : "text-warning",
      d.beats_baseline ? "Beat the baseline on the test set."
                       : "Did not beat the naive baseline (tomorrow = today)."));
    box.appendChild(el("div", "mt-1", `Model trained: ${d.trained_at.slice(0, 10)}`));
    (d.warnings || []).forEach((w) => box.appendChild(el("div", "text-warning", w)));
    box.appendChild(el("div", "mt-2 fst-italic", d.disclaimer));
  }

  async function load() {
    if (!symbol) return;
    box.replaceChildren(el("span", "text-muted", "Loading forecast..."));
    try {
      const url = `/api/predictions/${encodeURIComponent(symbol)}/${horizonSel.value}/forecast?model=${modelSel.value}`;
      const r = await fetch(url);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "HTTP " + r.status);
      show(d);
    } catch (err) {
      box.replaceChildren(el("div", "text-danger", "Forecast unavailable: " + err.message));
    }
  }

  document.querySelectorAll(".stock-item[data-symbol]").forEach((item) =>
    item.addEventListener("click", () => { symbol = item.dataset.symbol; load(); }));
  horizonSel.addEventListener("change", load);
  modelSel.addEventListener("change", load);
})();