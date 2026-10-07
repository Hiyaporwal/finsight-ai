(function () {
  const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
  const num = new Intl.NumberFormat("en-IN");
  const overview = {};
  let chart = null;
  let selected = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function renderBox(box, d) {
    box.replaceChildren();
    box.appendChild(el("div", "h5 mb-0", inr.format(d.close)));
    if (d.change_pct !== null) {
      const up = d.change >= 0;
      box.appendChild(el("div", "small " + (up ? "up" : "down"),
        `${up ? "+" : ""}${d.change.toFixed(2)} (${up ? "+" : ""}${d.change_pct.toFixed(2)}%)`));
    }
    const today = new Date().toISOString().slice(0, 10);
    const label = d.as_of === today ? "latest (session may be in progress)" : "close";
    box.appendChild(el("div", "small text-muted", `As of ${d.as_of} close · delayed/end-of-day`));
  }

  function renderError(box, msg) {
    box.replaceChildren();
    box.appendChild(el("div", "small text-danger", msg));
    const btn = el("button", "btn btn-sm btn-outline-secondary mt-1", "Retry");
    btn.type = "button";
    btn.addEventListener("click", (e) => { e.stopPropagation(); loadOverview(); });
    box.appendChild(btn);
  }

  async function loadOverview() {
    const boxes = document.querySelectorAll(".price-box");
    if (!boxes.length) return;
    boxes.forEach((b) => b.replaceChildren(el("span", "small text-muted", "Loading prices...")));
    try {
      const r = await fetch("/api/stocks/overview");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      j.stocks.forEach((s) => { overview[s.symbol] = s; });
      boxes.forEach((box) => {
        const d = overview[box.dataset.symbol];
        if (!d || d.error) renderError(box, d && d.error ? "Data unavailable: " + d.error : "No data");
        else renderBox(box, d);
      });
    } catch (err) {
      boxes.forEach((b) => renderError(b, "Could not load prices."));
    }
  }

  function renderOhlcv(d) {
    const wrap = document.getElementById("ohlcv");
    wrap.replaceChildren();
    if (!d || d.error) return;
    [["Open", inr.format(d.open)], ["High", inr.format(d.high)], ["Low", inr.format(d.low)],
     ["Close", inr.format(d.close)], ["Volume", num.format(d.volume)], ["As of", d.as_of]]
      .forEach(([k, v]) => {
        const col = el("div", "col-6 col-md-2");
        col.appendChild(el("div", "text-muted", k));
        col.appendChild(el("div", "fw-semibold", v));
        wrap.appendChild(col);
      });
  }

  async function loadChart() {
    if (!selected) return;
    const status = document.getElementById("chartStatus");
    const period = document.getElementById("periodSelect").value;
    const meta = overview[selected];
    document.getElementById("chartTitle").textContent = meta ? `${meta.name} (${selected})` : selected;
    status.textContent = "Loading chart...";
    try {
      const r = await fetch(`/api/stocks/${encodeURIComponent(selected)}/history?period=${period}`);
      const d = await r.json();
      if (!r.ok || d.error) throw new Error(d.error || "HTTP " + r.status);
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById("priceChart"), {
        type: "line",
        data: { labels: d.dates, datasets: [{ label: "Close (INR)", data: d.close,
          borderColor: "#14b8a6", backgroundColor: "rgba(45,212,191,.12)", fill: true,
          pointRadius: 0, borderWidth: 2, tension: 0.15 }] },
        options: { responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          scales: { x: { ticks: { maxTicksLimit: 8 } } } },
      });
      status.textContent = `${d.data_status}. Source: ${d.source}. Fetched ${new Date(d.fetched_at).toLocaleString()}.`;
      renderOhlcv(overview[selected]);
    } catch (err) {
      status.textContent = "Could not load chart: " + err.message;
    }
  }

  function setupSelection() {
    const items = document.querySelectorAll(".stock-item[data-symbol]");
    items.forEach((item) => item.addEventListener("click", () => {
      items.forEach((i) => i.classList.remove("selected"));
      item.classList.add("selected");
      selected = item.dataset.symbol;
      loadChart();
    }));
    const sel = document.getElementById("periodSelect");
    if (sel) sel.addEventListener("change", loadChart);
  }

  loadOverview();
  if (document.getElementById("priceChart")) setupSelection();
})();