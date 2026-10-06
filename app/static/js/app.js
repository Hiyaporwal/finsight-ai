// Show/hide password
document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = btn.closest(".input-group").querySelector("input");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.querySelector("i").className = show ? "bi bi-eye-slash" : "bi bi-eye";
  });
});

// Password strength meter (visual hint only; the server enforces the real rules)
const pwInput = document.querySelector("[data-strength-source]");
if (pwInput) {
  const bar = document.getElementById("strengthBar");
  const label = document.getElementById("strengthLabel");
  const levels = [
    ["Too weak", "bg-danger"], ["Weak", "bg-danger"], ["Fair", "bg-warning"],
    ["Good", "bg-info"], ["Strong", "bg-success"], ["Very strong", "bg-success"],
  ];
  pwInput.addEventListener("input", () => {
    const p = pwInput.value;
    let s = 0;
    if (p.length >= 8) s++;
    if (p.length >= 12) s++;
    if (/[A-Z]/.test(p) && /[a-z]/.test(p)) s++;
    if (/\d/.test(p)) s++;
    if (/[^A-Za-z0-9]/.test(p)) s++;
    bar.style.width = (p ? Math.max(s, 1) * 20 : 0) + "%";
    bar.className = "progress-bar " + levels[p ? s : 0][1];
    label.textContent = p ? "Strength: " + levels[s][0] : "Use 8+ characters with upper and lower case letters and a digit.";
  });
}

// Dashboard stock search
const search = document.getElementById("stockSearch");
if (search) {
  const items = document.querySelectorAll(".stock-item");
  const none = document.getElementById("noMatch");
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    let visible = 0;
    items.forEach((el) => {
      const match = el.dataset.search.includes(q);
      el.classList.toggle("d-none", !match);
      if (match) visible++;
    });
    none.classList.toggle("d-none", visible !== 0);
  });
}