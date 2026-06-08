const $ = (id) => document.getElementById(id);

function getValue(id) {
  const element = $(id);
  return element ? element.value.trim() : "";
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
    citation_evidence_notes: getValue("citation_evidence_notes")
  };

  localStorage.setItem("projectready_registration_profile", JSON.stringify(profile));
  $("registerStatus").textContent = "Profile created. Opening your workspace...";
  window.setTimeout(() => { window.location.href = "/workspace"; }, 500);
}

$("registrationForm").addEventListener("submit", storeRegistrationProfile);
