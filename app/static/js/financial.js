(function () {
  const box = document.getElementById("finBox");
  if (!box) return;
  let symbol = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const crore = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  function fmt(unit, v) {
    if (v === null || v === undefined) return "n/a";
    if (unit === "pct") return (v * 100).toFixed(1) + "%";
    if (unit === "ratio") return v.toFixed(2);
    if (unit === "inr") return "Rs. " + crore.format(v / 1e7) + " Cr";
    return v.toFixed(2);
  }
  function list(title, items, cls, empty) {
    const wrap = el("div", "mb-2");
    wrap.appendChild(el("div", "fw-semibold " + cls, title));
    if (!items.length) wrap.appendChild(el("div", "text-muted", empty));
    else { const ul = el("ul", "mb-0 ps-3"); items.forEach((t) => ul.appendChild(el("li", "", t))); wrap.appendChild(ul); }
    return wrap;
  }
  function th(t) { return el("th", "", t); }
  function td(t, cls) { return el("td", cls || "", t); }

  function show(d) {
    box.replaceChildren();
    const head = el("div", "d-flex align-items-center gap-3 mb-2 flex-wrap");
    const score = d.overall_score;
    const col = score === null ? "text-muted" : score >= 70 ? "text-success" : score >= 50 ? "text-warning" : "text-danger";
    head.appendChild(el("div", "display-6 fw-bold " + col, score === null ? "N/A" : score.toFixed(0) + " / 100"));
    const meta = el("div");
    meta.appendChild(el("div", "fw-semibold", d.rating));
    meta.appendChild(el("div", "text-muted", `${d.symbol} · fiscal year ended ${d.fiscal_year_end} · ${d.coverage_pct}% of score weight available`));
    head.appendChild(meta);
    box.appendChild(head);

    const t = el("table", "table table-sm align-middle");
    const hr = el("tr"); ["Metric", "Value", "Score", "Weight"].forEach((h) => hr.appendChild(th(h)));
    t.appendChild(el("thead")).appendChild(hr);
    const tb = el("tbody");
    d.metrics.forEach((m) => {
      const tr = el("tr");
      tr.appendChild(td(m.label));
      tr.appendChild(td(m.status === "scored" ? fmt(m.unit, m.value) : "n/a"));
      tr.appendChild(td(m.status === "scored" ? m.score.toFixed(0) : (m.status === "not_meaningful" ? "excluded" : "missing"),
                        m.status === "scored" ? "" : "text-muted"));
      tr.appendChild(td(String(m.weight)));
      tr.title = m.note || m.description;
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    const tw = el("div", "table-responsive"); tw.appendChild(t); box.appendChild(tw);
    box.appendChild(el("div", "text-muted mb-2", "Hover a row for its definition or the reason it is missing or excluded."));

    const ctx = el("div", "mb-2");
    ctx.appendChild(el("div", "fw-semibold", "Context (not scored)"));
    d.context.forEach((c) => ctx.appendChild(el("div", "", `${c.label}: ${fmt(c.unit, c.value)}${c.note ? " (" + c.note + ")" : ""}`)));
    box.appendChild(ctx);

    const cols = el("div", "row g-3");
    const a = el("div", "col-md-6"); a.appendChild(list("Strengths", d.strengths, "text-success", "No metric scored 70 or above."));
    const b = el("div", "col-md-6"); b.appendChild(list("Potential risks", d.risks, "text-danger", "No metric scored 40 or below."));
    cols.appendChild(a); cols.appendChild(b); box.appendChild(cols);

    const tt = el("table", "table table-sm mt-2");
    const h2 = el("tr"); ["Fiscal year end", "Revenue", "Net income", "Net margin"].forEach((h) => h2.appendChild(th(h)));
    tt.appendChild(el("thead")).appendChild(h2);
    const b2 = el("tbody");
    d.trend.forEach((r) => {
      const tr = el("tr");
      tr.appendChild(td(r.fiscal_year_end)); tr.appendChild(td(fmt("inr", r.revenue)));
      tr.appendChild(td(fmt("inr", r.net_income))); tr.appendChild(td(fmt("pct", r.net_margin)));
      b2.appendChild(tr);
    });
    tt.appendChild(b2);
    box.appendChild(el("div", "fw-semibold mt-2", "Historical trend"));
    const tw2 = el("div", "table-responsive"); tw2.appendChild(tt); box.appendChild(tw2);

    const det = el("details", "mb-2");
    det.appendChild(el("summary", "fw-semibold", "How this score is calculated"));
    det.appendChild(el("p", "mt-2", d.methodology.summary));
    const ul = el("ul", "ps-3");
    d.methodology.metrics.forEach((m) => ul.appendChild(el("li", "",
      `${m.label} (weight ${m.weight}): ` + m.points.map((p) => `${p[0]} -> ${p[1]}`).join(", "))));
    det.appendChild(ul);
    const lim = el("ul", "ps-3"); d.methodology.limitations.forEach((l) => lim.appendChild(el("li", "", l)));
    det.appendChild(el("div", "fw-semibold", "Limitations")); det.appendChild(lim);
    box.appendChild(det);

    box.appendChild(el("div", "fst-italic", `${d.disclaimer} Source: ${d.source}, fetched ${new Date(d.fetched_at).toLocaleString()}.`));
  }

  async function load() {
    if (!symbol) return;
    box.replaceChildren(el("span", "text-muted", "Loading financial data..."));
    try {
      const r = await fetch(`/api/financials/${encodeURIComponent(symbol)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "HTTP " + r.status);
      show(d);
    } catch (err) {
      box.replaceChildren(el("div", "text-danger", "Financial analysis unavailable: " + err.message));
      const btn = el("button", "btn btn-sm btn-outline-secondary mt-2", "Retry");
      btn.type = "button"; btn.addEventListener("click", load); box.appendChild(btn);
    }
  }

  document.querySelectorAll(".stock-item[data-symbol]").forEach((item) =>
    item.addEventListener("click", () => { symbol = item.dataset.symbol; load(); }));
})();