let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];
let latestSourceSearchResult = null;
let accumulatedSourceBank = [];

const $ = (id) => document.getElementById(id);

const levelDepthGuidance = {
  "Bachelors": "Use clear undergraduate depth: accurate definitions, relevant context, basic critical discussion, and a defensible but not overly complex methodology.",
  "Non-Research Masters": "Use applied master's depth: stronger synthesis, professional relevance, practical implications, and clear methodological justification.",
  "Research Masters (e.g. MPhil)": "Use research master's depth: critical synthesis, explicit gaps, theory-method alignment, rigorous methodology, and strong objective-by-objective argument.",
  "Professional Doctorate (e.g. DBA, DEd)": "Use professional doctorate depth: advanced applied scholarship, organisational or professional problem framing, evidence-informed practice contribution, and defensible methodology.",
  "PhD": "Use doctoral depth: original contribution, deep theoretical engagement, advanced critical synthesis, rigorous methodological defence, and publication-quality academic argument."
};

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

function renderSections() {
  const chapter = getChapter($("chapterSelect").value);
  currentChapter = chapter.chapter_number;
  currentSections = getSections(chapter);
  const box = $("sectionsBox");
  box.innerHTML = "";
  for (const section of currentSections) {
    const div = document.createElement("div");
    div.className = "section-item";
    div.innerHTML = `
      <label>
        <input type="checkbox" name="section" value="${section.section_id}" ${section.default_selected ? "checked" : ""} />
        ${section.section_title}
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
    thesis_format: $("thesis_format") ? $("thesis_format").value : "Standard five-chapter thesis/dissertation",
    format_notes: $("format_notes") ? $("format_notes").value.trim() : "",
    research_area: $("research_area").value.trim(),
    study_context: $("study_context").value.trim(),
    citation_evidence_notes: $("citation_evidence_notes") ? $("citation_evidence_notes").value.trim() : "",
    research_approach: $("research_approach").value,
    data_type: $("data_type") ? $("data_type").value : "Primary data",
    expected_chapters: 5,
    objectives: lines($("objectives").value),
    research_questions: [],
    hypotheses: [],
    variables: {},
    notes: $("format_notes") ? $("format_notes").value.trim() : ""
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


function sourceKey(src) {
  const doi = String(src?.doi || "").trim().toLowerCase();
  if (doi) return `doi:${doi}`;
  return `title:${String(src?.title || "").toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 100)}`;
}

function mergeSourceBank(existing, incoming, limit = 60) {
  const merged = [];
  const seen = new Set();
  for (const src of [...(existing || []), ...(incoming || [])]) {
    if (!src || typeof src !== "object") continue;
    const key = sourceKey(src);
    if (!key || key === "title:" || seen.has(key)) continue;
    seen.add(key);
    merged.push(src);
    if (merged.length >= limit) break;
  }
  return merged;
}

function currentSourcePayload() {
  const sources = mergeSourceBank(accumulatedSourceBank, latestSourceSearchResult?.sources || []);
  if (!sources.length) return {};
  return {
    source_bank: sources,
    retrieved_sources: {
      ...(latestSourceSearchResult || {}),
      sources: latestSourceSearchResult?.sources || sources,
      source_bank_count: sources.length,
      frontend_attached: true
    },
    source_search_terms: latestSourceSearchResult?.query || ($("sourceSearchQuery") ? $("sourceSearchQuery").value.trim() : "")
  };
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
  const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    answers: collectAnswers(),
    extra_instructions: $("extraInstructions").value.trim(),
    use_ai: $("useAi") ? $("useAi").checked : true,
    ...currentSourcePayload()
  };
  $("draftStatus").textContent = "Generating draft...";
  const result = await api(`/api/projects/${currentProjectId}/draft`, { method: "POST", body: JSON.stringify(payload) });
  $("draftOutput").value = result.draft;
  renderDraftPreview(result.draft);
  $("draftStatus").textContent = "Draft generated based on the information provided.";
  $("downloadDraftBtn").disabled = false;
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


async function findSources() {
  if (!currentProjectId) await createProject();
  const payload = {
    query: $("sourceSearchQuery") ? $("sourceSearchQuery").value.trim() : "",
    max_results: $("sourceMaxResults") ? Number($("sourceMaxResults").value) : 12,
    include_older_foundational: $("includeOlderFoundational") ? $("includeOlderFoundational").checked : true
  };
  $("sourceStatus").textContent = "Searching scholarly sources and attaching them to the project...";
  const result = await api(`/api/projects/${currentProjectId}/find-sources`, { method: "POST", body: JSON.stringify(payload) });
  latestSourceSearchResult = result;
  accumulatedSourceBank = mergeSourceBank(accumulatedSourceBank, result.source_bank || result.sources || []);
  renderSources(result);
  const errors = (result.provider_errors || []).length;
  $("sourceStatus").textContent = `Attached ${(result.source_bank_count || result.count || 0)} sources to the project. ${errors ? errors + " provider(s) could not be reached." : ""}`;
}

function renderSources(result) {
  const box = $("sourceResults");
  if (!box) return;
  const sources = result.sources || [];
  if (!sources.length) {
    box.innerHTML = `<p class="hint">No source records were found. Refine the search terms and try again.</p>`;
    return;
  }
  const meta = `
    <div class="source-meta">
      <strong>Search query:</strong> ${escapeHtml(result.query || "")}<br />
      <strong>Recent-reference window:</strong> ${escapeHtml(result.recent_reference_window || "")}<br />
      <strong>Databases searched:</strong> ${escapeHtml((result.databases || []).join(", "))}
    </div>`;
  const cards = sources.map((src, idx) => {
    const authors = Array.isArray(src.authors) ? src.authors.join(", ") : (src.authors || "");
    const doi = src.doi ? ` DOI: ${escapeHtml(src.doi)}` : "";
    const url = src.url ? `<a href="${escapeHtml(src.url)}" target="_blank" rel="noopener">Open source record</a>` : "";
    const abstract = src.abstract ? `<p>${escapeHtml(src.abstract)}</p>` : `<p class="hint">No abstract was returned by the metadata provider.</p>`;
    return `
      <div class="source-card">
        <div class="source-title">${idx + 1}. ${escapeHtml(src.title || "Untitled source")}</div>
        <div class="source-sub">${escapeHtml(authors)} ${src.year ? "(" + escapeHtml(src.year) + ")" : ""}</div>
        <div class="source-sub">${escapeHtml(src.source || src.database || "")} ${doi}</div>
        ${abstract}
        <div class="source-hint"><strong>Citation hint:</strong> ${escapeHtml(src.apa_hint || "")}</div>
        <div class="source-link">${url}</div>
      </div>`;
  }).join("");
  box.innerHTML = meta + cards;
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
$("uploadResultsBtn").addEventListener("click", () => uploadResults().catch(err => $("uploadStatus").textContent = err.message));
if ($("findSourcesBtn")) {
  $("findSourcesBtn").addEventListener("click", () => findSources().catch(err => $("sourceStatus").textContent = err.message));
}
$("checkBtn").addEventListener("click", () => runCheck().catch(err => $("draftStatus").textContent = err.message));
$("downloadDraftBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/chapter/${currentChapter}`));
$("downloadCheckBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/check/${currentChapter}`));
if ($("level")) {
  $("level").addEventListener("change", updateLevelHint);
  updateLevelHint();
}

loadTemplate().catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});
