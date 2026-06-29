const $ = (id) => document.getElementById(id);
const REGISTRATION_PROFILE_KEY = "projectready_registration_profile";

function getValue(id) {
  const element = $(id);
  return element ? element.value.trim() : "";
}

function safeReturnPath() {
  const raw = new URLSearchParams(window.location.search).get("return") || "/workspace";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/workspace";
  return raw;
}

function addRegisteredFlag(path) {
  const target = new URL(path, window.location.origin);
  target.searchParams.set("registered", "1");
  return target.pathname + target.search + target.hash;
}

function loadExistingProfile() {
  let profile = null;
  try {
    profile = JSON.parse(localStorage.getItem(REGISTRATION_PROFILE_KEY) || "null");
  } catch (_) {
    profile = null;
  }
  if (!profile || typeof profile !== "object") return;
  Object.entries(profile).forEach(([key, value]) => {
    const element = $(key);
    if (element && value !== undefined && value !== null) element.value = String(value);
  });
  if ($("registerStatus")) {
    $("registerStatus").textContent = "An existing registration profile was found. Review and save any changes.";
  }
}

function storeRegistrationProfile(event) {
  event.preventDefault();
  const responsibility = $("responsibility");
  if (responsibility && !responsibility.checked) {
    $("registerStatus").textContent = "Please confirm the responsible-use statement before continuing.";
    return;
  }

  const profile = {
    full_name: getValue("full_name"),
    email: getValue("email"),
    country: getValue("country"),
    account_type: getValue("account_type"),
    level: getValue("level") || "Bachelors",
    institution: getValue("institution"),
    programme: getValue("programme"),
    department: getValue("department"),
    citation_style: getValue("citation_style"),
    title: getValue("title"),
    thesis_format: getValue("thesis_format") || "Standard five-chapter thesis/dissertation",
    data_type: getValue("data_type") || "Primary survey data",
    research_area: getValue("research_area"),
    study_context: getValue("study_context"),
    objectives: getValue("objectives"),
    format_notes: getValue("format_notes"),
    citation_evidence_notes: getValue("citation_evidence_notes"),
    academic_integrity_confirmed: true,
    user_contribution_confirmed: true,
    registered_at: new Date().toISOString()
  };

  localStorage.setItem(REGISTRATION_PROFILE_KEY, JSON.stringify(profile));
  $("registerStatus").textContent = "Registration profile saved. Returning to your workspace...";
  const destination = addRegisteredFlag(safeReturnPath());
  window.setTimeout(() => { window.location.href = destination; }, 450);
}

$("registrationForm").addEventListener("submit", storeRegistrationProfile);
loadExistingProfile();
