let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];

const $ = (id) => document.getElementById(id);

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
  return {
    title: $("title").value.trim(),
    programme: $("programme").value.trim(),
    department: $("department").value.trim(),
    institution: $("institution").value.trim(),
    level: "Project work",
    research_area: $("research_area").value.trim(),
    study_context: $("study_context").value.trim(),
    research_approach: $("research_approach").value,
    data_type: "Primary data",
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
  const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    answers: collectAnswers(),
    extra_instructions: $("extraInstructions").value.trim(),
    use_ai: $("useAi").checked
  };
  $("draftStatus").textContent = "Generating draft...";
  const result = await api(`/api/projects/${currentProjectId}/draft`, { method: "POST", body: JSON.stringify(payload) });
  $("draftOutput").value = result.draft;
  $("draftStatus").textContent = `Draft generated using ${result.source}.`;
  $("downloadDraftBtn").disabled = false;
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

function download(path) {
  window.location.href = path;
}

$("createProjectBtn").addEventListener("click", () => createProject().catch(err => $("projectStatus").textContent = err.message));
$("draftBtn").addEventListener("click", () => generateDraft().catch(err => $("draftStatus").textContent = err.message));
$("checkBtn").addEventListener("click", () => runCheck().catch(err => $("draftStatus").textContent = err.message));
$("downloadDraftBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/chapter/${currentChapter}`));
$("downloadCheckBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/check/${currentChapter}`));

loadTemplate().catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});
