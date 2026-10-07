(function () {
  const table = document.getElementById("compareTable");
  if (!table) return;
  const body = table.querySelector("tbody");
  const info = document.getElementById("compareInfo");
  const note = document.getElementById("compareNote");
  const horizonSel = document.getElementById("compareHorizon");
  const LABELS = { random_forest: "Random Forest", xgboost: "XGBoost", lstm: "LSTM", gru: "GRU", naive_baseline: "Naive baseline (tomorrow = today)" };
  const COLORS = { random_forest: "#f59e0b", xgboost: "#6366f1", lstm: "#ef4444", gru: "#10b981" };
  let symbol = null, chart = null;

  function cell(text, cls) {
    const td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function render(d) {
    body.replaceChildren();
    const base = d.metrics.naive_baseline;
    ["random_forest", "xgboost", "lstm", "gru", "naive_baseline"].forEach((k) => {
      const m = d.metrics[k];
      if (!m) return;
      const tr = document.createElement("tr");
      const beats = k !== "naive_baseline" && m.mape < base.mape;
      tr.appendChild(cell(LABELS[k] + (beats ? "  (beats baseline)" : ""), beats ? "fw-bold text-success" : ""));
      tr.appendChild(cell(m.mae.toFixed(2)));
      tr.appendChild(cell(m.rmse.toFixed(2)));
      tr.appendChild(cell(m.mape.toFixed(2)));
      tr.appendChild(cell(m.directional_accuracy !== undefined ? m.directional_accuracy.toFixed(1) : "-"));
      body.appendChild(tr);
    });
    table.classList.remove("d-none");
    info.textContent = `${d.symbol} · ${d.horizon_sessions} session(s) ahead · trained ${d.trained_at.slice(0, 10)} · ` +
      `train ${d.train_range[0]} to ${d.train_range[1]} · val ${d.val_range[0]} to ${d.val_range[1]} · ` +
      `test ${d.test_range[0]} to ${d.test_range[1]}`;
    note.textContent = d.disclaimer;

    const s = d.test_series;
    if (chart) chart.destroy();
    if (!s) return;
    const datasets = [{ label: "Actual", data: s.actual_price, borderColor: "#111827", borderWidth: 2, pointRadius: 0 }];
    Object.keys(COLORS).forEach((k) => {
      const col = s[k + "_pred_price"];
      if (col) datasets.push({ label: LABELS[k], data: col, borderColor: COLORS[k], borderWidth: 1.2, pointRadius: 0, borderDash: [4, 3] });
    });
    chart = new Chart(document.getElementById("compareChart"), {
      type: "line", data: { labels: s.date, datasets },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 8 } } } },
    });
  }

  async function load() {
    if (!symbol) return;
    info.textContent = "Loading comparison...";
    try {
      const r = await fetch(`/api/predictions/${encodeURIComponent(symbol)}/${horizonSel.value}/comparison`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "HTTP " + r.status);
      render(d);
    } catch (err) {
      info.textContent = "Comparison unavailable: " + err.message;
    }
  }

  document.querySelectorAll(".stock-item[data-symbol]").forEach((item) =>
    item.addEventListener("click", () => { symbol = item.dataset.symbol; load(); }));
  horizonSel.addEventListener("change", load);
})();