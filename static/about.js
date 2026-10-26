async function configureEvaluationLink() {
  const links = document.querySelectorAll("[data-evaluation-link]");
  try {
    const response = await fetch("/api/info");
    if (!response.ok) return;
    const payload = await response.json();
    const enabled = payload.evaluation_enabled === true;
    links.forEach((link) => {
      link.hidden = !enabled;
      link.style.display = enabled ? "" : "none";
    });
  } catch (_error) {
    links.forEach((link) => {
      link.hidden = true;
      link.style.display = "none";
    });
  }
}

window.addEventListener("DOMContentLoaded", () => {
  configureEvaluationLink();
});
