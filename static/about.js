const INDIVIDUAL_PREFERENCE_KEY = "xprs.individual_id";
const LANGUAGE_PREFERENCE_KEY = "xprs.language";

function readPreference(key, fallback = "") {
  try {
    return window.localStorage.getItem(key) || fallback;
  } catch (_error) {
    return fallback;
  }
}

function savePreference(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_error) {
    // Navigation still works when browser storage is unavailable.
  }
}

function dashboardUrl(individualId) {
  const params = new URLSearchParams({
    individual_id: individualId,
    disease: "breast_cancer",
    cohort: "1000_genomes",
    language: readPreference(LANGUAGE_PREFERENCE_KEY, "en"),
  });
  return `/dashboard?${params.toString()}`;
}

async function configureBreastCancerPortalLink() {
  const link = document.getElementById("sidebar-breast-portal");
  if (!link) return;

  const storedIndividual = readPreference(INDIVIDUAL_PREFERENCE_KEY);
  if (storedIndividual) link.href = dashboardUrl(storedIndividual);

  try {
    const response = await fetch("/api/individuals?cohort=1000_genomes");
    if (!response.ok) return;
    const payload = await response.json();
    const individuals = Array.isArray(payload.individuals) ? payload.individuals : [];
    const individualId = individuals.includes(storedIndividual)
      ? storedIndividual
      : individuals[0] || "";
    if (!individualId) return;
    savePreference(INDIVIDUAL_PREFERENCE_KEY, individualId);
    link.href = dashboardUrl(individualId);
  } catch (_error) {
    // The link safely retains its overview fallback when lookup is unavailable.
  }
}

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
  configureBreastCancerPortalLink();
  configureEvaluationLink();
});
