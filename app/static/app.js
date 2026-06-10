let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];
let latestSourceSearchResult = null;
let accumulatedSourceBank = [];
let uploadedRevisionText = "";
let uploadedRevisionFilename = "";

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

function chapterDisplayName(ch) {
  const exactNames = {
    1: "Introduction",
    2: "Literature Review",
    3: "Research Methods/Methodology",
    4: "Results/Data Analysis and Discussion",
    5: "Summary, Conclusion and Recommendation",
    6: "Others",
    7: "Supplementary Methods Chapter"
  };
  return exactNames[Number(ch.chapter_number)] || ch.chapter_title || "Others";
}

function chapterSortKey(ch) {
  const order = {1: 1, 2: 2, 3: 3, 7: 4, 4: 5, 5: 6, 6: 7};
  return order[Number(ch.chapter_number)] || 99;
}

function isResultsChapter() {
  const ch = template ? getChapter(currentChapter) : null;
  return currentChapter === 4 || /result|analysis|discussion/i.test(ch?.chapter_title || "");
}

function isMethodsChapter() {
  const ch = template ? getChapter(currentChapter) : null;
  return currentChapter === 3 || /method/i.test(ch?.chapter_title || "");
}

function isPrimaryOrQualitative() {
  const data = ($("data_type")?.value || "").toLowerCase();
  const approach = ($("research_approach")?.value || "").toLowerCase();
  return /primary|survey|qualitative|mixed/.test(data) || /quantitative|qualitative|mixed/.test(approach);
}

function updateChapterSpecificUi() {
  const resultsBox = $("resultsUploadBox");
  if (resultsBox) resultsBox.hidden = !isResultsChapter();
  const instrumentBtn = $("downloadInstrumentBtn");
  if (instrumentBtn) instrumentBtn.hidden = true;
  const supplementBtn = $("downloadMethodsSupplementBtn");
  if (supplementBtn) supplementBtn.disabled = !currentProjectId;
  const otherBox = $("otherChapterBox");
  if (otherBox) otherBox.hidden = currentChapter !== 6;
}

function selectedSectionIds() {
  return Array.from(document.querySelectorAll("input[name='section']:checked")).map(x => x.value);
}


function ensureOtherChapterTemplate() {
  if (!template || !Array.isArray(template.chapters)) return;
  const hasOther = template.chapters.some(ch => Number(ch.chapter_number) === 6);
  if (!hasOther) {
    template.chapters.push({
      chapter_number: 6,
      chapter_title: "Others",
      section_groups: [{
        group_title: "Custom Chapter Sections",
        sections: [
          {
            section_id: "ch6_custom_scope",
            section_title: "Custom Chapter Scope and Purpose",
            default_selected: true,
            guiding_questions: [
              "What should this additional chapter cover?",
              "Why is this chapter needed in the thesis, dissertation or project work?",
              "What specific sections, models, evidence, tables or outputs should be included?"
            ],
            rules: [
              "Draft only the content requested by the user or institution for this additional chapter.",
              "Make the chapter coherent with the project title, objectives, theory, methodology, results and recommendations.",
              "Use relevant in-text citations, evidence and an APA reference list where applicable."
            ]
          },
          {
            section_id: "ch6_user_sections",
            section_title: "User-Specified Sections",
            default_selected: true,
            guiding_questions: [
              "List the headings or sections you want the app to include in this chapter.",
              "What should each section achieve?",
              "Are there special formatting, evidence, table, equation or diagram requirements?"
            ],
            rules: [
              "Use the headings supplied by the user as the organising structure.",
              "Keep the content aligned with the rest of the project.",
              "Do not invent data, results, sources, ethical approvals, sample sizes or institutional details."
            ]
          }
        ]
      }]
    });
  }
  template.chapters.sort((a, b) => chapterSortKey(a) - chapterSortKey(b));
}


function ensureSupplementaryMethodsTemplate() {
  if (!template || !Array.isArray(template.chapters)) return;
  const hasSupplement = template.chapters.some(ch => Number(ch.chapter_number) === 7);
  if (!hasSupplement) {
    template.chapters.push({
      chapter_number: 7,
      chapter_title: "Supplementary Methods Chapter",
      section_groups: [{
        group_title: "Supplementary Methods, Instrument and Data-Source Preparation",
        sections: [
          {
            section_id: "ch7_purpose_scope",
            section_title: "Purpose and Scope of the Supplementary Methods Chapter",
            default_selected: true,
            guiding_questions: [
              "Should this supplementary chapter support a primary survey, qualitative, mixed-method, secondary-data, econometric, time-series or panel-data study?",
              "What decisions, instruments, data sources, coding notes or appendix materials should this support document prepare?",
              "Which parts are intended only for the appendix or research preparation, rather than the submission-ready methodology chapter?"
            ],
            rules: [
              "Make clear that this is a supplementary working/support chapter for instrument, measurement, variable, data-source and appendix preparation; it must not replace the main Research Methods/Methodology chapter.",
              "Use red bracketed placeholders where project-specific details, scale sources, data sources, coding decisions, permissions, or validation evidence are missing."
            ]
          },
          {
            section_id: "ch7_objective_construct_alignment",
            section_title: "Objective-to-Construct or Objective-to-Variable Alignment",
            default_selected: true,
            guiding_questions: [
              "List each research objective and the construct, variable, concept, theme or indicator needed to answer it.",
              "For each objective, what role does each construct or variable play: independent, dependent, mediator, moderator, control, demographic, theme or outcome?",
              "What analysis or evidence will be needed for each objective?"
            ],
            rules: [
              "Create a clean alignment table linking objectives to constructs/variables, measurement/data needs, proposed analysis and required source evidence.",
              "Align every instrument section, questionnaire item, interview prompt, data source and analysis requirement with the objectives."
            ]
          },
          {
            section_id: "ch7_instrument_traceability",
            section_title: "Instrument Development and Source Traceability",
            default_selected: true,
            guiding_questions: [
              "Which questionnaire scales, interview-guide themes, validated items, published instruments or institutional records should inform measurement?",
              "Which sources from the project source bank support the constructs, scale items, operational definitions or data-source choices?",
              "Which constructs still need verified scale/item sources?"
            ],
            rules: [
              "Use the project source bank where available to identify relevant scale, questionnaire, measurement or data-source references.",
              "Where a questionnaire scale, validated item source or data source is missing, insert a red placeholder such as [insert verified scale source for this construct]."
            ]
          },
          {
            section_id: "ch7_questionnaire",
            section_title: "Draft Questionnaire for Primary Survey Studies",
            default_selected: true,
            guiding_questions: [
              "What respondent screening, consent, demographic and study-variable sections should the questionnaire contain?",
              "What items should be drafted for each construct or variable in the objectives?",
              "What response scale should be used for each item or section?"
            ],
            rules: [
              "For primary survey or mixed-method studies, draft a complete questionnaire aligned with the objectives and constructs.",
              "Do not provide only a generic questionnaire structure; draft construct-specific items using the variables and objectives supplied by the user."
            ]
          },
          {
            section_id: "ch7_interview_guide",
            section_title: "Draft Interview Guide where Applicable",
            default_selected: false,
            guiding_questions: [
              "Is the study qualitative or mixed-methods, and who will be interviewed?",
              "What themes, constructs or objectives should the interview guide cover?",
              "What probes will help obtain deeper explanations without leading respondents?"
            ],
            rules: [
              "For qualitative or mixed-method studies, draft an interview guide aligned with the objectives, constructs, themes and respondent category.",
              "Include opening script, consent reminder, main questions, probes, closing question and interviewer notes."
            ]
          },
          {
            section_id: "ch7_data_source_register",
            section_title: "Variable and Data Source Register for Secondary, Econometric, Time-Series or Panel Studies",
            default_selected: true,
            guiding_questions: [
              "Which variables, indicators, proxies or datasets are needed for each objective or model?",
              "What is the preferred source for each variable, including institution, database, report, URL, frequency, country/firm coverage and study period?",
              "What variables still require verified data sources or alternative proxies?"
            ],
            rules: [
              "Create a variable/data-source register for secondary-data, econometric, time-series or panel-data studies.",
              "Insert red placeholders where the exact data source, period, frequency, unit or access link is missing."
            ]
          },
          {
            section_id: "ch7_operational_definition_coding",
            section_title: "Operational Definition, Coding and Transformation Notes",
            default_selected: true,
            guiding_questions: [
              "How should each construct, variable or questionnaire item be coded?",
              "What transformations are required, such as logs, percentages, index construction, reverse coding, differencing, lagging or standardisation?",
              "Which assumptions, diagnostics or cleaning steps are needed before analysis?"
            ],
            rules: [
              "Create an operational definition and coding table that links variables/constructs to indicators, codes, scales, transformations, expected direction and analysis use."
            ]
          },
          {
            section_id: "ch7_validation_quality_checks",
            section_title: "Validation, Reliability and Quality Checks",
            default_selected: true,
            guiding_questions: [
              "What checks are needed to confirm that the questionnaire, interview guide or dataset is suitable for analysis?",
              "What reliability, validity, pilot-test, expert-review, diagnostic or robustness checks should be reported later?",
              "Which outputs should the user obtain before analysis and results writing?"
            ],
            rules: [
              "Include relevant validation, reliability, quality, diagnostic and robustness checks for the selected data type and analytical approach."
            ]
          },
          {
            section_id: "ch7_appendix_placement",
            section_title: "Appendix Placement Guide",
            default_selected: true,
            guiding_questions: [
              "Which materials should appear in the main methodology chapter and which should be moved to the appendix?",
              "Should the full questionnaire, interview guide, coding sheet, raw software output, data dictionary or source register go into the appendix?",
              "What appendix labels should be used?"
            ],
            rules: [
              "Advise clearly which materials should go to the appendix and which should remain in the main chapter or supplementary chapter."
            ]
          }
        ]
      }]
    });
  }
  template.chapters.sort((a, b) => chapterSortKey(a) - chapterSortKey(b));
}

async function loadTemplate() {
  template = await api("/api/templates/default");
  ensureOtherChapterTemplate();
  ensureSupplementaryMethodsTemplate();
  template.chapters.sort((a, b) => chapterSortKey(a) - chapterSortKey(b));
  const chapterSelect = $("chapterSelect");
  chapterSelect.innerHTML = "";
  for (const ch of template.chapters) {
    const opt = document.createElement("option");
    opt.value = ch.chapter_number;
    opt.textContent = chapterDisplayName(ch);
    chapterSelect.appendChild(opt);
  }
  chapterSelect.addEventListener("change", () => {
    currentChapter = Number(chapterSelect.value);
    renderSections();
    updateChapterSpecificUi();
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
  updateChapterSpecificUi();
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
    draft_maturity: $("draftMaturity") ? $("draftMaturity").value : "Supervisor-ready draft",
    student_contribution: {
      draft_maturity: $("draftMaturity") ? $("draftMaturity").value : "Supervisor-ready draft",
      central_argument: $("centralArgument") ? $("centralArgument").value.trim() : "",
      local_context_notes: $("localContextNotes") ? $("localContextNotes").value.trim() : "",
      evidence_anchors: $("evidenceAnchors") ? $("evidenceAnchors").value.trim() : "",
      supervisor_comments: $("supervisorComments") ? $("supervisorComments").value.trim() : "",
      preferred_style: $("preferredStyle") ? $("preferredStyle").value.trim() : "",
      writing_sample: $("writingSample") ? $("writingSample").value.trim() : "",
      phrases_to_avoid: $("preferredStyle") ? $("preferredStyle").value.trim() : "",
      human_revision_pass: $("humanRevisionPass") ? $("humanRevisionPass").checked : true
    },
    research_approach: $("research_approach").value,
    data_type: $("data_type") ? $("data_type").value : "Primary data",
    variables: {
      raw_variables: lines($("variables_constructs") ? $("variables_constructs").value : "")
    },
    expected_chapters: 7,
    other_chapter_title: $("otherChapterTitle") ? $("otherChapterTitle").value.trim() : "",
    other_chapter_instructions: $("otherChapterInstructions") ? $("otherChapterInstructions").value.trim() : "",
    objectives: lines($("objectives").value),
    research_questions: [],
    hypotheses: [],
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
  updateChapterSpecificUi();
}

function genericLanguageAudit(text) {
  const patterns = [
    /\bin today's world\b/gi,
    /\bit is important to note\b/gi,
    /\bdelve into\b/gi,
    /\bplays a crucial role\b/gi,
    /\bvarious factors\b/gi,
    /\bsignificant impact\b/gi,
    /\bthis highlights the importance\b/gi,
    /\bmoreover\b/gi,
    /\bfurthermore\b/gi
  ];
  return patterns.reduce((count, pattern) => count + ((text || '').match(pattern) || []).length, 0);
}

function showDraftQualityHint(text) {
  const count = genericLanguageAudit(text);
  const status = $("draftStatus");
  if (!status) return;
  if (count > 8) {
    status.textContent = "Draft generated. Quality note: review the chapter for generic transitions and add more project-specific evidence before final submission.";
  } else {
    status.textContent = "Draft generated based on the information provided. Review, evidence and revise before submission.";
  }
}

async function generateDraft() {
  if (!currentProjectId) await createProject();
  const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    answers: collectAnswers(),
    extra_instructions: $("extraInstructions").value.trim(),
    use_ai: $("useAi") ? $("useAi").checked : true,
    revision_mode: $("revisionMode") ? $("revisionMode").checked : false,
    revision_instructions: $("revisionInstructions") ? $("revisionInstructions").value.trim() : "",
    revision_text: uploadedRevisionText,
    revision_filename: uploadedRevisionFilename,
    other_chapter_title: $("otherChapterTitle") ? $("otherChapterTitle").value.trim() : "",
    other_chapter_instructions: $("otherChapterInstructions") ? $("otherChapterInstructions").value.trim() : "",
    draft_maturity: $("draftMaturity") ? $("draftMaturity").value : "Supervisor-ready draft",
    student_contribution: {
      draft_maturity: $("draftMaturity") ? $("draftMaturity").value : "Supervisor-ready draft",
      central_argument: $("centralArgument") ? $("centralArgument").value.trim() : "",
      local_context_notes: $("localContextNotes") ? $("localContextNotes").value.trim() : "",
      evidence_anchors: $("evidenceAnchors") ? $("evidenceAnchors").value.trim() : "",
      supervisor_comments: $("supervisorComments") ? $("supervisorComments").value.trim() : "",
      preferred_style: $("preferredStyle") ? $("preferredStyle").value.trim() : "",
      writing_sample: $("writingSample") ? $("writingSample").value.trim() : "",
      phrases_to_avoid: $("preferredStyle") ? $("preferredStyle").value.trim() : "",
      human_revision_pass: $("humanRevisionPass") ? $("humanRevisionPass").checked : true
    },
    human_revision_pass: $("humanRevisionPass") ? $("humanRevisionPass").checked : true,
    ...currentSourcePayload()
  };
  $("draftStatus").textContent = "Generating draft...";
  const result = await api(`/api/projects/${currentProjectId}/draft`, { method: "POST", body: JSON.stringify(payload) });
  $("draftOutput").value = result.draft;
  renderDraftPreview(result.draft);
  showDraftQualityHint(result.draft);
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


async function uploadRevision() {
  if (!currentProjectId) await createProject();
  const input = $("revisionFile");
  if (!input || !input.files || input.files.length === 0) {
    $("revisionStatus").textContent = "Please select a chapter file first.";
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);
  formData.append("chapter_number", String(currentChapter || 1));

  $("revisionStatus").textContent = "Uploading and extracting the chapter for revision...";
  const response = await fetch(`/api/projects/${currentProjectId}/upload-revision`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const result = await response.json();
  uploadedRevisionText = result.extracted_text || result.preview || "";
  uploadedRevisionFilename = result.filename || "";
  if ($("revisionMode")) $("revisionMode").checked = true;
  $("revisionStatus").textContent = `Uploaded ${result.filename}. Extracted ${result.characters_extracted} characters for revision.`;
  $("revisionPreview").textContent = result.preview || "No preview available.";
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
  const withAdditions = safe
    .replace(/\[\[ADD\]\]/g, '<span class="addition-text">')
    .replace(/\[\[\/ADD\]\]/g, '</span>');
  return withAdditions.replace(/(\[[^\]\n]{3,}\])/g, '<span class="placeholder-text">$1</span>');
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
if ($("uploadResultsBtn")) $("uploadResultsBtn").addEventListener("click", () => uploadResults().catch(err => $("uploadStatus").textContent = err.message));
if ($("uploadRevisionBtn")) $("uploadRevisionBtn").addEventListener("click", () => uploadRevision().catch(err => $("revisionStatus").textContent = err.message));
if ($("downloadInstrumentBtn")) $("downloadInstrumentBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/instrument/${currentChapter}`));
if ($("downloadMethodsSupplementBtn")) $("downloadMethodsSupplementBtn").addEventListener("click", () => {
  const status = $("methodsSupplementStatus");
  if (!currentProjectId) {
    if (status) status.textContent = "Create the project profile first, then download the supplementary methods chapter.";
    return;
  }
  if (status) status.textContent = "Preparing supplementary methods chapter...";
  download(`/api/projects/${currentProjectId}/export/methods-supplement`);
});
if ($("data_type")) $("data_type").addEventListener("change", updateChapterSpecificUi);
if ($("research_approach")) $("research_approach").addEventListener("change", updateChapterSpecificUi);
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

updateChapterSpecificUi();

loadTemplate().catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});
