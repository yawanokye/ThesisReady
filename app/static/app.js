let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];

const $ = (id) => document.getElementById(id);

const levelDepthGuidance = {
  "Bachelors": "Use clear undergraduate depth: accurate definitions, relevant context, basic critical discussion, and a defensible but not overly complex methodology.",
  "Non-Research Masters": "Use applied master's depth: stronger synthesis, professional relevance, practical implications, and clear methodological justification.",
  "Research Masters (e.g. MPhil)": "Use research master's depth: critical synthesis, explicit gaps, theory-method alignment, rigorous methodology, and strong objective-by-objective argument.",
  "Professional Doctorate (e.g. DBA, DEd)": "Use professional doctorate depth: advanced applied scholarship, organisational or professional problem framing, evidence-informed practice contribution, and defensible methodology.",
  "PhD": "Use doctoral depth: original contribution, deep theoretical engagement, advanced critical synthesis, rigorous methodological defence, and publication-quality academic argument."
};

const freeAllowedSectionIds = new Set([
  "ch1_background",
  "ch1_problem",
  "ch1_purpose",
  "ch1_objectives",
  "ch1_questions"
]);

function accessPlan() {
  return localStorage.getItem("projectready_access_plan") || "Free Starter";
}

function isFreePlan() {
  return accessPlan().toLowerCase().includes("free");
}

function updateFreePlanNotice() {
  const notice = $("planNotice");
  if (!notice) return;
  if (isFreePlan()) {
    notice.textContent = "Free Starter allows drafting only the first five Chapter One sections. Paid plans unlock full chapters, revisions, compliance checks, and exports.";
    notice.hidden = false;
  } else {
    notice.textContent = `Active plan: ${accessPlan()}`;
    notice.hidden = false;
  }
}

function applyRegistrationProfile() {
  let profile = null;
  try {
    profile = JSON.parse(localStorage.getItem("projectready_registration_profile") || "null");
  } catch (error) {
    profile = null;
  }
  if (!profile) return;

  const mapping = {
    title: "title",
    level: "level",
    thesis_format: "thesis_format",
    data_type: "data_type",
    research_area: "research_area",
    study_context: "study_context",
    objectives: "objectives",
    format_notes: "format_notes",
    citation_evidence_notes: "citation_evidence_notes"
  };

  for (const [key, elementId] of Object.entries(mapping)) {
    const element = $(elementId);
    if (element && profile[key]) {
      element.value = profile[key];
    }
  }

  const notes = [];
  if (profile.institution) notes.push(`Institution: ${profile.institution}`);
  if (profile.department) notes.push(`Department: ${profile.department}`);
  if (profile.programme) notes.push(`Programme: ${profile.programme}`);
  if (profile.citation_style) notes.push(`Preferred citation style: ${profile.citation_style}`);
  const formatNotes = $("format_notes");
  if (formatNotes && notes.length) {
    const existing = formatNotes.value.trim();
    formatNotes.value = existing ? `${existing}\n${notes.join("\n")}` : notes.join("\n");
  }
}

function updateLevelHint() {
  // Keep the level-depth guidance internal. The selected level still guides the AI prompt,
  // but the explanatory text is not displayed to users.
  if ($("levelDepthHint")) {
    $("levelDepthHint").textContent = "";
    $("levelDepthHint").hidden = true;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function lines(value) {
  return (value || "").split("\n").map(v => v.trim()).filter(Boolean);
}

function selectedSectionIds() {
  return Array.from(document.querySelectorAll("input[name='section']:checked")).map(x => x.value);
}

async function loadTemplate() {
  template = await api("/api/templates/default");
  const chapterSelect = $("chapterSelect");
  chapterSelect.innerHTML = "";
  for (const ch of template.chapters) {
    const opt = document.createElement("option");
    opt.value = ch.chapter_number;
    opt.textContent = `Chapter ${ch.chapter_number}: ${ch.chapter_title}`;
    chapterSelect.appendChild(opt);
  }
  chapterSelect.addEventListener("change", () => {
    currentChapter = Number(chapterSelect.value);
    renderSections();
  });
  renderSections();
}

function getChapter(number) {
  return template.chapters.find(ch => ch.chapter_number === Number(number));
}

function getSections(chapter) {
  return chapter.section_groups.flatMap(group => group.sections);
}

function methodStream() {
  return ($("data_type")?.value || "Primary survey data").toLowerCase();
}

function recommendedSectionIds(chapterNumber) {
  const stream = methodStream();
  const isSecondary = stream.includes("secondary") || stream.includes("econometric") || stream.includes("time-series") || stream.includes("time series") || stream.includes("panel");
  const isQualitative = stream.includes("qualitative");

  if (isSecondary) {
    const recommendations = {
      2: ["ch2_intro", "ch2_conceptual", "ch2_theoretical", "ch2_empirical_objectives", "ch2_secondary_stylised", "ch2_econometric_literature", "ch2_framework", "ch2_gap_table", "ch2_summary"],
      3: ["ch3_intro", "ch3_philosophy", "ch3_design", "ch3_secondary_data_sources", "ch3_variable_construction", "ch3_model_specification", "ch3_estimation_technique", "ch3_econometric_diagnostics", "ch3_analysis", "ch3_reproducibility", "ch3_ethics", "ch3_summary"],
      4: ["ch4_intro", "ch4_uploaded_results", "ch4_descriptive_trends", "ch4_diagnostic_results", "ch4_econometric_results", "ch4_policy_economic_interpretation", "ch4_discussion", "ch4_summary"],
      5: ["ch5_intro", "ch5_summary_findings", "ch5_conclusions", "ch5_recommendations", "ch5_policy_implications", "ch5_limitations", "ch5_future"]
    };
    return recommendations[chapterNumber] ? new Set(recommendations[chapterNumber]) : null;
  }

  if (isQualitative) {
    const recommendations = {
      2: ["ch2_intro", "ch2_conceptual", "ch2_theoretical", "ch2_empirical_objectives", "ch2_variable_review", "ch2_framework", "ch2_summary"],
      3: ["ch3_intro", "ch3_philosophy", "ch3_design", "ch3_setting_population", "ch3_sampling", "ch3_instrument", "ch3_collection", "ch3_analysis", "ch3_ethics", "ch3_summary"],
      4: ["ch4_intro", "ch4_uploaded_results", "ch4_results_objectives", "ch4_discussion", "ch4_summary"]
    };
    return recommendations[chapterNumber] ? new Set(recommendations[chapterNumber]) : null;
  }

  return null;
}

function shouldCheckSection(section) {
  if (isFreePlan()) {
    return currentChapter === 1 && freeAllowedSectionIds.has(section.section_id);
  }
  const recommended = recommendedSectionIds(currentChapter);
  if (recommended) return recommended.has(section.section_id);
  return Boolean(section.default_selected);
}

function renderSections() {
  const chapter = getChapter($("chapterSelect").value);
  currentChapter = chapter.chapter_number;
  currentSections = getSections(chapter);
  const box = $("sectionsBox");
  box.innerHTML = "";
  for (const section of currentSections) {
    const div = document.createElement("div");
    div.className = "section-item";
    const freeLocked = isFreePlan() && !(currentChapter === 1 && freeAllowedSectionIds.has(section.section_id));
    div.innerHTML = `
      <label>
        <input type="checkbox" name="section" value="${section.section_id}" ${shouldCheckSection(section) ? "checked" : ""} ${freeLocked ? "disabled" : ""} />
        ${section.section_title} ${freeLocked ? '<span class="locked-label">Upgrade</span>' : ''}
      </label>
      <small>${section.rules[0] || ""}</small>
    `;
    box.appendChild(div);
  }
  box.querySelectorAll("input[name='section']").forEach(cb => cb.addEventListener("change", renderAnswers));
  renderAnswers();
}

function renderAnswers() {
  const selected = new Set(selectedSectionIds());
  const box = $("answersBox");
  box.innerHTML = "";
  for (const section of currentSections.filter(s => selected.has(s.section_id))) {
    const div = document.createElement("div");
    div.className = "question-card";
    const questions = (section.guiding_questions || []).map((q, idx) => `
      <label>${q}
        <textarea data-section="${section.section_id}" data-question="q${idx + 1}" rows="2"></textarea>
      </label>
    `).join("");
    div.innerHTML = `<h3>${section.section_title}</h3>${questions}`;
    box.appendChild(div);
  }
}

function collectProfile() {
  const selectedLevel = $("level")?.value || "Bachelors";
  return {
    title: $("title").value.trim(),
    programme: "",
    department: "",
    institution: "",
    level: selectedLevel,
    academic_level_guidance: levelDepthGuidance[selectedLevel] || "",
    reference_currency_rule: "Aim for at least 70% of substantive references from the last five years. Where current references do not exist for a specific issue, use the most relevant credible available sources, including foundational theories, classic models, and essential older studies.",
    access_plan: accessPlan(),
    thesis_format: $("thesis_format") ? $("thesis_format").value : "Standard five-chapter thesis/dissertation",
    format_notes: $("format_notes") ? $("format_notes").value.trim() : "",
    research_area: $("research_area").value.trim(),
    study_context: $("study_context").value.trim(),
    citation_evidence_notes: $("citation_evidence_notes") ? $("citation_evidence_notes").value.trim() : "",
    research_approach: $("research_approach").value,
    data_type: $("data_type") ? $("data_type").value : "Primary survey data",
    method_stream: $("data_type") ? $("data_type").value : "Primary survey data",
    expected_chapters: 5,
    objectives: lines($("objectives").value),
    research_questions: [],
    hypotheses: [],
    variables: {},
    notes: ""
  };
}

function collectAnswers() {
  const answers = {};
  document.querySelectorAll("#answersBox textarea").forEach(area => {
    const section = area.dataset.section;
    const question = area.previousSibling?.textContent?.trim() || area.dataset.question;
    if (!answers[section]) answers[section] = {};
    if (area.value.trim()) answers[section][question] = area.value.trim();
  });
  return answers;
}

async function createProject() {
  const profile = collectProfile();
  if (!profile.title) {
    $("projectStatus").textContent = "Please enter a project title.";
    return;
  }
  $("projectStatus").textContent = "Creating project...";
  const result = await api("/api/projects", { method: "POST", body: JSON.stringify(profile) });
  currentProjectId = result.id;
  $("projectStatus").textContent = `Project created: ${result.id}`;
}

async function generateDraft() {
  if (!currentProjectId) await createProject();
  if (isFreePlan() && (currentChapter !== 1 || selectedSectionIds().some(id => !freeAllowedSectionIds.has(id)))) {
    $("draftStatus").textContent = "Free Starter allows drafting only the first five sections of Chapter One.";
    return;
  }
  if (isFreePlan() && $("revisionMode")?.checked) {
    $("draftStatus").textContent = "Revised-version upload is available on paid plans.";
    return;
  }
  const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    answers: collectAnswers(),
    extra_instructions: $("extraInstructions").value.trim(),
    use_ai: $("useAi") ? $("useAi").checked : true,
    revision_mode: $("revisionMode") ? $("revisionMode").checked : false,
    revision_instructions: $("revisionInstructions") ? $("revisionInstructions").value.trim() : ""
  };
  $("draftStatus").textContent = "Generating draft...";
  const result = await api(`/api/projects/${currentProjectId}/draft`, { method: "POST", body: JSON.stringify(payload) });
  $("draftOutput").value = result.draft;
  renderDraftPreview(result.draft);
  $("draftStatus").textContent = "Draft generated based on the information provided.";
  $("downloadDraftBtn").disabled = false;
}

async function uploadChapterForRevision() {
  if (!currentProjectId) await createProject();
  if (isFreePlan()) {
    $("revisionStatus").textContent = "Revised-version upload is available on paid plans.";
    return;
  }
  const input = $("revisionFile");
  if (!input || !input.files || input.files.length === 0) {
    $("revisionStatus").textContent = "Please select the existing chapter file first.";
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);
  formData.append("chapter_number", String(currentChapter));

  $("revisionStatus").textContent = "Uploading and extracting the existing chapter...";
  const response = await fetch(`/api/projects/${currentProjectId}/upload-chapter`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const result = await response.json();
  $("revisionStatus").textContent = `Uploaded ${result.filename}. Extracted ${result.characters_extracted} characters for Chapter ${result.chapter_number}.`;
  $("revisionPreview").textContent = result.preview || "No preview available.";
  if ($("revisionMode")) $("revisionMode").checked = true;
}

async function uploadResults() {
  if (!currentProjectId) await createProject();
  const input = $("resultsFile");
  if (!input || !input.files || input.files.length === 0) {
    $("uploadStatus").textContent = "Please select a results file first.";
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);
  formData.append("chapter_number", String(currentChapter || 4));

  $("uploadStatus").textContent = "Uploading and extracting results...";
  const response = await fetch(`/api/projects/${currentProjectId}/upload-results`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const result = await response.json();
  $("uploadStatus").textContent = `Uploaded ${result.filename}. Extracted ${result.characters_extracted} characters for Chapter ${result.chapter_number}.`;
  $("uploadPreview").textContent = result.preview || "No preview available.";
}

async function runCheck() {
  if (!currentProjectId) {
    $("draftStatus").textContent = "Create a project and generate a draft first.";
    return;
  }
  const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    draft: $("draftOutput").value
  };
  $("draftStatus").textContent = "Checking compliance...";
  const result = await api(`/api/projects/${currentProjectId}/check`, { method: "POST", body: JSON.stringify(payload) });
  renderCheck(result);
  $("draftStatus").textContent = "Compliance check completed.";
  $("downloadCheckBtn").disabled = false;
}

function renderCheck(result) {
  $("scoreBox").textContent = `Compliance score: ${result.score_percent}%`;
  const tbody = document.querySelector("#checkTable tbody");
  tbody.innerHTML = "";
  for (const item of result.items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(item.section_title)}</td>
      <td>${escapeHtml(item.requirement)}</td>
      <td class="status-${item.status}">${escapeHtml(item.status)}</td>
      <td>${escapeHtml(item.evidence)}</td>
      <td>${escapeHtml(item.suggested_action)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[ch]));
}

function highlightPlaceholders(value) {
  const safe = escapeHtml(value);
  return safe.replace(/(\[[^\]\n]{3,}\])/g, '<span class="placeholder-text">$1</span>');
}

function renderDraftPreview(value) {
  const preview = $("draftPreview");
  if (!preview) return;
  preview.innerHTML = highlightPlaceholders(value || "");
}

function download(path) {
  window.location.href = path;
}

if ($("draftOutput")) {
  $("draftOutput").addEventListener("input", () => renderDraftPreview($("draftOutput").value));
}

$("createProjectBtn").addEventListener("click", () => createProject().catch(err => $("projectStatus").textContent = err.message));
$("draftBtn").addEventListener("click", () => generateDraft().catch(err => $("draftStatus").textContent = err.message));
if ($("uploadRevisionBtn")) {
  $("uploadRevisionBtn").addEventListener("click", () => uploadChapterForRevision().catch(err => $("revisionStatus").textContent = err.message));
}
$("uploadResultsBtn").addEventListener("click", () => uploadResults().catch(err => $("uploadStatus").textContent = err.message));
$("checkBtn").addEventListener("click", () => runCheck().catch(err => $("draftStatus").textContent = err.message));
$("downloadDraftBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/chapter/${currentChapter}`));
$("downloadCheckBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/check/${currentChapter}`));
if ($("level")) {
  $("level").addEventListener("change", updateLevelHint);
  updateLevelHint();
}
updateFreePlanNotice();
if ($("data_type")) {
  $("data_type").addEventListener("change", () => {
    if (template) renderSections();
  });
}

applyRegistrationProfile();

loadTemplate().catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});
