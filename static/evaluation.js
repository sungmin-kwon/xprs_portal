const RATING_ITEMS = [
  [10, "Usability", "The portal was easy to navigate."],
  [11, "Usability", "The portal responded quickly enough for exploratory use."],
  [12, "Explainability", "The summary helped me understand the individual's XPRS profile."],
  [13, "Explainability", "The gene-level explanations helped me understand which genes contributed to the score."],
  [14, "Explainability", "The portal made the difference between PRS percentile, gene contribution, and disease association clear."],
  [15, "Visualizations", "The PRS density and Manhattan plots helped me interpret the result."],
  [16, "Evidence and trust", "The numbered references and abstract viewer made the explanation more trustworthy."],
  [17, "Evidence and trust", "The cited evidence appeared relevant to the generated explanation."],
  [18, "Follow-up chat", "The follow-up chatbot answered my question in a useful way."],
  [19, "Follow-up chat", "The chatbot stayed within an appropriate research-information scope."],
  [20, "PDF report", "The PDF report was useful as a portable summary of the session."],
  [21, "Overall", "Overall, the portal was useful for interpreting XPRS outputs."],
  [22, "Overall", "I would recommend this portal for research-oriented review of XPRS outputs."],
  [23, "Overall", "I would use this portal again for a similar analysis."],
];

const REQUIRED_NAMES = [
  "q1", "q2", "participant_id", "background", "prs_familiarity",
  "xprs_familiarity", "completion_time",
  ...Array.from({ length: 14 }, (_, index) => `q${index + 10}`),
  "q24", "q25", "q26", "most_useful", "confusing_or_missing",
  "understanding_impact", "most_important_improvement",
];

const form = document.getElementById("evaluation-form");
const message = document.getElementById("form-message");
const accessMessage = document.getElementById("access-message");
const submitButton = document.getElementById("submit-button");
let accessReady = false;

function renderNumberScales() {
  document.querySelectorAll("[data-scale-name]").forEach((container) => {
    const name = container.dataset.scaleName;
    for (let score = 1; score <= 5; score += 1) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = name;
      input.value = String(score);
      input.required = score === 1;
      label.append(input, document.createTextNode(String(score)));
      container.append(label);
    }
  });
}

function renderRatingItems() {
  const container = document.getElementById("rating-items");
  let previousGroup = "";
  RATING_ITEMS.forEach(([number, group, text]) => {
    const block = document.createElement("fieldset");
    block.className = "rating-item";
    if (group !== previousGroup) {
      const groupLabel = document.createElement("div");
      groupLabel.className = "rating-group-label";
      groupLabel.textContent = group;
      block.append(groupLabel);
      previousGroup = group;
    }

    const legend = document.createElement("legend");
    legend.className = "rating-question-text";
    const numberBadge = document.createElement("span");
    numberBadge.className = "question-number";
    numberBadge.textContent = String(number);
    legend.append(numberBadge, document.createTextNode(text));
    const required = document.createElement("b");
    required.textContent = "*";
    required.setAttribute("aria-label", "required");
    legend.append(required);
    block.append(legend);

    const choices = document.createElement("div");
    choices.className = "rating-options";
    choices.setAttribute("aria-label", "1 strongly disagree through 5 strongly agree");
    for (let score = 1; score <= 5; score += 1) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `q${number}`;
      input.value = String(score);
      input.required = score === 1;
      label.append(input, document.createTextNode(String(score)));
      choices.append(label);
    }
    block.append(choices);
    container.append(block);
  });
}

function selectedValue(name) {
  const selected = form.elements[name];
  if (!selected) return "";
  return typeof selected.value === "string" ? selected.value.trim() : "";
}

function updateOtherBackground() {
  const other = document.getElementById("background-other");
  const active = selectedValue("background") === "other";
  other.hidden = !active;
  other.required = active;
  if (!active) other.value = "";
}

function updateProgress() {
  let total = REQUIRED_NAMES.length;
  let answered = REQUIRED_NAMES.filter((name) => selectedValue(name)).length;
  const other = document.getElementById("background-other");
  if (!other.hidden) {
    total += 1;
    if (other.value.trim()) answered += 1;
  }
  const percentage = Math.round((answered / total) * 100);
  document.getElementById("progress-bar").style.width = `${percentage}%`;
  document.getElementById("progress-label").textContent = `${percentage}% complete`;
}

function showMessage(text, kind) {
  message.textContent = text;
  message.className = `form-message is-${kind}`;
  message.scrollIntoView({ behavior: "smooth", block: "center" });
}

function buildPayload() {
  const ratings = {};
  for (let number = 10; number <= 23; number += 1) {
    ratings[`q${number}`] = Number(selectedValue(`q${number}`));
  }
  return {
    schema_version: "pilot-v1",
    prototype_acknowledged: selectedValue("q1") === "yes",
    consented: selectedValue("q2") === "yes",
    participant_id: selectedValue("participant_id"),
    portal_session_id: selectedValue("portal_session_id") || null,
    background: selectedValue("background"),
    background_other: selectedValue("background_other") || null,
    prs_familiarity: Number(selectedValue("prs_familiarity")),
    xprs_familiarity: Number(selectedValue("xprs_familiarity")),
    completed_tasks: Array.from(form.querySelectorAll('input[name="completed_tasks"]:checked')).map((input) => input.value),
    completion_time: selectedValue("completion_time"),
    ratings,
    comprehension: {
      q24: selectedValue("q24"),
      q25: selectedValue("q25"),
      q26: selectedValue("q26"),
    },
    most_useful: selectedValue("most_useful"),
    confusing_or_missing: selectedValue("confusing_or_missing"),
    understanding_impact: selectedValue("understanding_impact"),
    most_important_improvement: selectedValue("most_important_improvement"),
  };
}

async function submitEvaluation(event) {
  event.preventDefault();
  message.className = "form-message";
  if (!accessReady) {
    showMessage("This evaluation link is not authorized. Ask the study team for a current link.", "error");
    return;
  }
  if (!form.reportValidity()) {
    const invalid = form.querySelector(":invalid");
    if (invalid) invalid.scrollIntoView({ behavior: "smooth", block: "center" });
    showMessage("Please answer all required questions before submitting.", "error");
    return;
  }
  if (selectedValue("q1") !== "yes" || selectedValue("q2") !== "yes") {
    showMessage("Submission requires acknowledgement of the prototype and agreement to participate.", "error");
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Submitting…";
  try {
    const response = await fetch("/api/evaluation/responses", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    const receipt = await response.json();
    form.querySelectorAll("input, textarea, button").forEach((element) => { element.disabled = true; });
    showMessage(`Thank you. Your response was saved. Receipt ID: ${receipt.response_id}`, "success");
  } catch (error) {
    showMessage(`The response could not be saved: ${error.message}`, "error");
    submitButton.disabled = false;
    submitButton.textContent = "Submit response";
  }
}

async function establishAccess() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const token = fragment.get("token") || "";
  const headers = token ? { "X-XPRS-Evaluation-Token": token } : {};
  try {
    const response = await fetch("/api/evaluation/access", {
      method: "POST",
      credentials: "same-origin",
      headers,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (token) window.history.replaceState({}, "", window.location.pathname + window.location.search);
    accessReady = true;
    submitButton.disabled = false;
    submitButton.textContent = "Submit response";
  } catch (_error) {
    accessMessage.textContent = "This evaluation link is missing, invalid, or expired. Ask the study team for a current link.";
    accessMessage.className = "form-message is-error";
    submitButton.textContent = "Access required";
  }
}

renderNumberScales();
renderRatingItems();

const params = new URLSearchParams(window.location.search);
const sessionId = params.get("session_id");
if (sessionId) document.getElementById("portal-session-id").value = sessionId.slice(0, 100);

form.addEventListener("input", () => {
  updateOtherBackground();
  updateProgress();
});
form.addEventListener("submit", submitEvaluation);
updateOtherBackground();
updateProgress();
establishAccess();
