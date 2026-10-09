(function () {
  const box = document.getElementById("sentBox");
  if (!box) return;
  let symbol = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const COL = { positive: "#16a34a", negative: "#dc2626", neutral: "#94a3b8" };
  const pct = (v) => (v * 100).toFixed(0) + "%";

  function show(d) {
    box.replaceChildren();
    if (!d.headlines.length) {
      box.appendChild(el("div", "text-muted", d.message || "No headlines found."));
      box.appendChild(el("div", "fst-italic mt-2", d.disclaimer));
      return;
    }
    const s = d.summary;
    const col = s.overall === "Positive" ? "text-success" : s.overall === "Negative" ? "text-danger" : "text-secondary";
    const top = el("div", "mb-2");
    top.appendChild(el("span", "h5 fw-bold " + col, s.overall));
    top.appendChild(el("span", "text-muted ms-2",
      `${s.count} headline(s) · average score ${s.mean_score >= 0 ? "+" : ""}${s.mean_score.toFixed(2)} (scale -1 to +1)`));
    box.appendChild(top);
    if (s.low_sample) box.appendChild(el("div", "text-warning mb-2", "Small sample (fewer than 10 headlines), so treat this summary with caution."));

    const bar = el("div", "d-flex mb-1");
    bar.style.cssText = "height:16px;border-radius:8px;overflow:hidden";
    ["positive", "neutral", "negative"].forEach((k) => {
      const seg = el("div"); seg.style.cssText = `width:${s.proportions[k] * 100}%;background:${COL[k]}`; bar.appendChild(seg);
    });
    box.appendChild(bar);
    box.appendChild(el("div", "mb-3",
      `Positive ${pct(s.proportions.positive)} (${s.counts.positive}) · Neutral ${pct(s.proportions.neutral)} (${s.counts.neutral}) · ` +
      `Negative ${pct(s.proportions.negative)} (${s.counts.negative})`));

    if (s.trend) {
      box.appendChild(el("div", "fw-semibold", "Daily average sentiment"));
      const tr = el("div", "d-flex flex-wrap gap-2 mb-3");
      s.trend.forEach((t) => tr.appendChild(el("span", "badge text-bg-light",
        `${t.date}: ${t.mean_score >= 0 ? "+" : ""}${t.mean_score.toFixed(2)} (${t.count})`)));
      box.appendChild(tr);
    } else if (s.trend_note) {
      box.appendChild(el("div", "text-muted mb-3", s.trend_note));
    }

    const list = el("div");
    d.headlines.forEach((h) => {
      const row = el("div", "mb-2 pb-2 border-bottom");
      const line = el("div");
      const chip = el("span", "badge me-2", h.label);
      chip.style.background = COL[h.label];
      line.appendChild(chip);
      if (h.link && /^https?:\/\//.test(h.link)) {
        const a = el("a", "", h.title); a.href = h.link; a.target = "_blank"; a.rel = "noopener noreferrer"; line.appendChild(a);
      } else line.appendChild(el("span", "", h.title));
      row.appendChild(line);
      row.appendChild(el("div", "text-muted",
        `${h.source} · ${h.published ? new Date(h.published).toLocaleString() : "date unknown"} · score ${h.score >= 0 ? "+" : ""}${h.score.toFixed(2)}`));
      list.appendChild(row);
    });
    box.appendChild(list);
    box.appendChild(el("div", "fst-italic",
      `${d.disclaimer} Source: ${d.source}; model: ${d.model}; fetched ${new Date(d.fetched_at).toLocaleString()}.`));
  }

  async function load() {
    if (!symbol) return;
    box.replaceChildren(el("span", "text-muted", "Loading news and scoring headlines (the first run can take a minute)..."));
    try {
      const r = await fetch(`/api/sentiment/${encodeURIComponent(symbol)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "HTTP " + r.status);
      show(d);
    } catch (err) {
      box.replaceChildren(el("div", "text-danger", "News sentiment unavailable: " + err.message));
      const btn = el("button", "btn btn-sm btn-outline-secondary mt-2", "Retry");
      btn.type = "button"; btn.addEventListener("click", load); box.appendChild(btn);
    }
  }

  document.querySelectorAll(".stock-item[data-symbol]").forEach((item) =>
    item.addEventListener("click", () => { symbol = item.dataset.symbol; load(); }));
})();