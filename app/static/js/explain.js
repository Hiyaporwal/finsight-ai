(function () {
  const box = document.getElementById("explainBox");
  if (!box) return;
  const horizonSel = document.getElementById("predHorizon");
  const modelSel = document.getElementById("predModel");
  let symbol = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const sign = (v) => (v >= 0 ? "+" : "") + v.toFixed(3);

  function show(d) {
    box.replaceChildren();
    box.appendChild(el("div", "mb-2",
      `${d.symbol} · ${d.model} · ${d.horizon_sessions} session(s) · data as of ${d.as_of}. ` +
      `${d.method ? d.method + ". " : ""}Baseline output ${sign(d.base_return_pct)}%, ` +
      `this forecast ${sign(d.predicted_return_pct)}%.`));

    const maxAbs = Math.max(...d.top_features.map((f) => Math.abs(f.contribution_pct_points)), 1e-9);
    d.top_features.forEach((f) => {
      const row = el("div", "d-flex align-items-center gap-2 mb-1");

      const label = el("div", "", f.label);
      label.style.width = "230px";
      row.appendChild(label);

      const track = el("div", "flex-grow-1");
      track.style.cssText = "background:#eef4f8;height:14px;border-radius:7px;position:relative";
      const bar = el("div", "");
      const w = (Math.abs(f.contribution_pct_points) / maxAbs) * 50;
      bar.style.cssText = `position:absolute;top:0;height:14px;border-radius:7px;width:${w}%;` +
        `background:${f.direction === "up" ? "#16a34a" : "#dc2626"};` +
        (f.direction === "up" ? "left:50%" : `left:${50 - w}%`);
      track.appendChild(bar);
      row.appendChild(track);

      const txt = el("div", f.direction === "up" ? "up" : "down", `${sign(f.contribution_pct_points)} pp`);
      txt.style.width = "90px";
      txt.style.textAlign = "right";
      row.appendChild(txt);

      const val = el("div", "text-muted", `value ${f.value.toFixed(3)}`);
      val.style.width = "120px";
      row.appendChild(val);

      box.appendChild(row);
    });

    if (d.other_features_pct_points) {
      box.appendChild(el("div", "text-muted mt-1",
        `All other features combined: ${sign(d.other_features_pct_points)} pp`));
    }
    box.appendChild(el("div", "mt-2 fst-italic", d.note));
  }

  async function load() {
    if (!symbol) return;
    box.replaceChildren(el("span", "text-muted", "Loading explanation..."));
    try {
      const r = await fetch(
        `/api/predictions/${encodeURIComponent(symbol)}/${horizonSel.value}/explain?model=${modelSel.value}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "HTTP " + r.status);
      show(d);
    } catch (err) {
      box.replaceChildren(el("div", "text-warning", err.message));
    }
  }

  document.querySelectorAll(".stock-item[data-symbol]").forEach((item) =>
    item.addEventListener("click", () => { symbol = item.dataset.symbol; load(); }));
  horizonSel.addEventListener("change", load);
  modelSel.addEventListener("change", load);
})();