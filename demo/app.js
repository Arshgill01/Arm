"use strict";

const candidates = [
  {
    name: "Ministral Q4_0 + KleidiAI",
    accuracy: 70,
    latencySeconds: 1.282,
    qualityEligible: false,
    fixedRejection: "frozen experiment quality gate",
  },
  {
    name: "Ministral Q4_K_M",
    accuracy: 76.67,
    latencySeconds: 1.799,
    qualityEligible: true,
    fixedRejection: null,
  },
];

const qualityInput = document.querySelector("#quality-floor");
const latencyInput = document.querySelector("#latency-ceiling");
const qualityValue = document.querySelector("#quality-value");
const latencyValue = document.querySelector("#latency-value");
const decisionStatus = document.querySelector("#decision-status");
const decisionModel = document.querySelector("#decision-model");
const decisionExplanation = document.querySelector("#decision-explanation");
const candidateTable = document.querySelector("#candidate-table");

function evaluateCandidate(candidate, minimumAccuracy, maximumLatency) {
  const reasons = [];
  if (!candidate.qualityEligible) reasons.push(candidate.fixedRejection);
  if (candidate.accuracy < minimumAccuracy) reasons.push("accuracy policy");
  if (candidate.latencySeconds > maximumLatency) reasons.push("latency policy");
  return { ...candidate, reasons, feasible: reasons.length === 0 };
}

function renderDecision() {
  const minimumAccuracy = Number(qualityInput.value);
  const maximumLatency = Number(latencyInput.value);
  const evaluated = candidates.map((candidate) =>
    evaluateCandidate(candidate, minimumAccuracy, maximumLatency),
  );
  const selected = evaluated.find((candidate) => candidate.feasible) ?? null;

  qualityValue.value = `${minimumAccuracy.toFixed(2)}%`;
  latencyValue.value = `${maximumLatency.toFixed(1)} s`;
  decisionStatus.textContent = selected ? "Selected" : "No feasible candidate";
  decisionStatus.classList.toggle("empty", selected === null);
  decisionModel.textContent = selected ? selected.name : "Deployment refused";
  decisionExplanation.textContent = selected
    ? "The package is quality-eligible and clears the active accuracy, latency, memory, load, and size obligations."
    : "Every candidate violates at least one explicit obligation. Pareto64 emits the reasons and does not launch a near-miss.";

  candidateTable.replaceChildren(
    ...evaluated.map((candidate) => {
      const row = document.createElement("tr");
      const decision = candidate.feasible
        ? "Feasible"
        : `Rejected: ${candidate.reasons.join(", ")}`;
      [
        candidate.name,
        `${candidate.accuracy.toFixed(2)}%`,
        `${candidate.latencySeconds.toFixed(2)} s`,
        decision,
      ].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      return row;
    }),
  );
}

qualityInput.addEventListener("input", renderDecision);
latencyInput.addEventListener("input", renderDecision);

document.querySelectorAll("[data-quality]").forEach((button) => {
  button.addEventListener("click", () => {
    qualityInput.value = button.dataset.quality;
    latencyInput.value = button.dataset.latency;
    renderDecision();
  });
});

document.querySelector("#copy-command").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const command = document.querySelector("#reproduce-command").textContent;
  try {
    await navigator.clipboard.writeText(command);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Select command above";
  }
  window.setTimeout(() => {
    button.textContent = "Copy command";
  }, 1600);
});

renderDecision();
