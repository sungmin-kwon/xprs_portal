// Formulas are written as TeX in data-tex; block formulas sit in .score__formula.
function renderFormulas() {
  if (!window.katex) return;
  document.querySelectorAll("[data-tex]").forEach((element) => {
    window.katex.render(element.dataset.tex, element, {
      displayMode: element.classList.contains("score__formula"),
      throwOnError: false,
    });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  renderFormulas();
});
