let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];
let latestSourceSearchResult = null;
let accumulatedSourceBank = [];
let uploadedRevisionText = "";
let uploadedRevisionFilename = "";
let draftRequestInFlight = false;

const $ = (id) => document.getElementById(id);

const APP_STATIC_VERSION = "20260625-depth-citations-v1";
const CURRENT_PROJECT_STORAGE_KEY = "projectready-current-project";

const levelDepthGuidance = {
  "Bachelors": "Use clear undergraduate depth: accurate definitions, relevant context, basic critical discussion, and a defensible but not overly complex methodology.",
  "Non-Research Masters": "Use applied master's depth: stronger synthesis, professional relevance, practical implications, and clear methodological justification.",
  "Research Masters (e.g. MPhil)": "Use research master's depth: critical synthesis, explicit gaps, theory-method alignment, rigorous methodology, and strong objective-by-objective argument.",
  "Professional Doctorate (e.g. DBA, DEd)": "Use professional doctorate depth: advanced applied scholarship, organisational or professional problem framing, evidence-informed practice contribution, and defensible methodology.",
  "PhD": "Use doctoral depth: original contribution, deep theoretical engagement, advanced critical synthesis, rigorous methodological defence, and publication-quality academic argument."
};

const chapterPageTargets = {
  "Bachelors": {1: "10–15", 2: "15–22", 3: "10–15", 4: "20–25", 5: "8–12"},
  "Non-Research Masters": {1: "10–15", 2: "20–30", 3: "12–18", 4: "20–30", 5: "8–15"},
  "Research Masters (e.g. MPhil)": {1: "15–20", 2: "35–45", 3: "15–22", 4: "20–32", 5: "8–12"},
  "Professional Doctorate (e.g. DBA, DEd)": {1: "15–22", 2: "40–60", 3: "25–35", 4: "35–45", 5: "10–15"},
  "PhD": {1: "25–35", 2: "60–80", 3: "30–45", 4: "60–80", 5: "20–30"}
};

function updateLevelHint() {
  const hint = $("levelDepthHint");
  if (!hint) return;
  const level = $("level")?.value || "Bachelors";
  const chapter = Number(currentChapter || 1);
  const pages = chapterPageTargets[level]?.[chapter];
  if (!pages || chapter > 5) {
    hint.textContent = "Depth for this output is based on the selected scope and sections.";
  } else {
    hint.textContent = `Target depth for Chapter ${chapter}: about ${pages} pages, with citations distributed across substantive paragraphs. Final pagination depends on tables, figures, equations and references.`;
  }
  hint.hidden = false;
}

async function api(path, options = {}) {
  const actionRoute = /\/(draft|check)$/.test(path);
  const paymentHeaders = actionRoute && window.ProjectReadyPayments && currentProjectId
    ? ProjectReadyPayments.paymentHeaders(currentProjectId, currentChapter)
    : {};
  const idempotencyHeaders = actionRoute ? {"Idempotency-Key": requestId()} : {};
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...paymentHeaders,
      ...idempotencyHeaders,
      ...(options.headers || {})
    },
  });
  if (!response.ok) {
    let data = null;
    let message = response.statusText || "Request failed";
    try {
      data = await response.json();
      if (data && data.detail) {
        if (typeof data.detail === "string") message = data.detail;
        else if (data.detail.message) message = data.detail.message;
        else if (Array.isArray(data.detail)) message = data.detail.map(item => item.msg || JSON.stringify(item)).join("; ");
        else message = JSON.stringify(data.detail);
      }
    } catch (_) {}
    const error = new Error(message);
    error.status = response.status;
    error.detail = data?.detail || data;
    throw error;
  }
  return response.json();
}

function requestId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
  return `pr-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function currentChapterTitle() {
  const select = $("chapterSelect");
  return select?.options?.[select.selectedIndex]?.text || `Chapter ${currentChapter}`;
}

function currentAccessOptions() {
  return {
    projectId: currentProjectId,
    chapterNumber: Number(currentChapter),
    chapterTitle: currentChapterTitle(),
    academicLevel: $("level")?.value || "Bachelors"
  };
}

function hideAccessRequiredNotice() {
  const notice = $("accessRequiredNotice");
  if (notice) notice.hidden = true;
}

function showAccessRequiredNotice(error) {
  const notice = $("accessRequiredNotice");
  const message = $("accessRequiredMessage");
  const registerLink = $("accessRegisterBtn");
  if (!notice) return;
  const detailMessage = error?.detail?.message || error?.message || "Register or unlock this chapter to continue.";
  if (message) message.textContent = detailMessage;
  if (registerLink && window.ProjectReadyPayments) {
    registerLink.href = ProjectReadyPayments.registrationUrl(currentAccessOptions());
    registerLink.textContent = ProjectReadyPayments.hasRegistrationProfile()
      ? "Review registration profile"
      : "Register / create profile";
  }
  notice.hidden = false;
  notice.scrollIntoView({behavior: "smooth", block: "center"});
}

async function openCurrentCheckout({direct = false, detail = null} = {}) {
  if (!currentProjectId) await createProject();
  if (!currentProjectId) throw new Error("Create the project profile before checkout.");
  if (!window.ProjectReadyPayments) throw new Error("The payment interface did not load. Refresh the page and try again.");
  const options = currentAccessOptions();
  if (direct || typeof ProjectReadyPayments.openAccessGate !== "function") {
    return ProjectReadyPayments.openCheckout(options);
  }
  return ProjectReadyPayments.openAccessGate(options, detail || {});
}

async function handleWorkspaceError(error, statusElement) {
  const status = typeof statusElement === "string" ? $(statusElement) : statusElement;
  const message = error?.detail?.message || error?.message || "The request could not be completed.";
  if (status) status.textContent = message;
  if ([401, 402].includes(Number(error.status))) {
    showAccessRequiredNotice(error);
    try {
      await openCurrentCheckout({detail: error.detail || {message}});
    } catch (checkoutError) {
      if (status) status.textContent = `${message} ${checkoutError.message || ""}`.trim();
    }
  }
}

async function protectedDownload(path, chapterNumber = currentChapter) {
  const headers = {"Idempotency-Key": requestId()};
  if (window.ProjectReadyPayments && currentProjectId) {
    Object.assign(headers, ProjectReadyPayments.paymentHeaders(currentProjectId, Number(chapterNumber)));
  }
  const response = await fetch(path, {headers});
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch (_) {}
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : (detail?.message || response.statusText || "Download failed");
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  const filename = match ? decodeURIComponent(match[1].replace(/"/g, "").trim()) : `ProjectReady-Chapter-${chapterNumber}.docx`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function updatePaymentPanel() {
  const panel = $("chapterAccessPanel");
  const title = $("chapterPlanTitle");
  const status = $("chapterAccessStatus");
  const button = $("unlockChapterBtn");
  if (!panel || !title || !status || !button) return;
  panel.classList.remove("is-active", "is-warning");
  const level = $("level")?.value || "Bachelors";
  const fallbackPlanMap = {
    "Bachelors": ["Bachelors Project", "US$4.99"],
    "Non-Research Masters": ["Masters Dissertation / MPhil Thesis", "US$9.99"],
    "Research Masters (e.g. MPhil)": ["Masters Dissertation / MPhil Thesis", "US$9.99"],
    "Professional Doctorate (e.g. DBA, DEd)": ["Professional Doctorate / PhD", "US$19.99"],
    "PhD": ["Professional Doctorate / PhD", "US$19.99"]
  };
  const fallbackPlan = fallbackPlanMap[level] || ["Paid chapter", "See checkout"];
  title.textContent = `${fallbackPlan[0]} · ${fallbackPlan[1]} per chapter`;
  try {
    const response = await fetch(`/api/payments/plans?level=${encodeURIComponent(level)}`, {cache: "no-store"});
    const plans = await response.json();
    const plan = plans.paid_plans?.find(item => item.plan_key === plans.recommended_plan);
    if (response.ok && plan) {
      const prices = [];
      if (plan.paystack_price_display) prices.push(`${plan.paystack_price_display} via Paystack`);
      if (plan.price_display) prices.push(`${plan.price_display} international`);
      title.textContent = `${plan.name} · ${prices.join(" / ") || "See checkout"} per chapter`;
    }
  } catch (_) {}
  button.disabled = !currentProjectId;

  if (!currentProjectId) {
    status.textContent = "Create the project profile to activate checkout.";
    return;
  }

  const revision = $("revisionMode")?.checked;
  const selectedCount = selectedSectionIds().length;
  const freeEligible = currentChapter === 1 && selectedCount > 0 && selectedCount <= 5 && !revision;
  const credential = window.ProjectReadyPayments?.getCredential(currentProjectId, currentChapter);
  if (credential) {
    try {
      const entitlement = await ProjectReadyPayments.checkEntitlement(currentProjectId, currentChapter);
      if (entitlement.allowed && entitlement.project_id === currentProjectId && entitlement.chapter_key === `chapter-${currentChapter}`) {
        const r = entitlement.remaining || {};
        panel.classList.add("is-active");
        status.textContent = `Payment confirmed. Remaining: draft ${r.draft ?? 0}, revision ${r.revision ?? 0}, compliance ${r.compliance ?? 0}, export ${r.export ?? 0}.`;
        button.textContent = "Purchase another chapter access";
        return;
      }
      if (entitlement.status === "pending") {
        panel.classList.add("is-warning");
        status.textContent = "Payment is still pending confirmation.";
        button.textContent = "Restart checkout";
        return;
      }
    } catch (_) {}
  }

  button.textContent = "Unlock this chapter";
  if (freeEligible) {
    panel.classList.add("is-warning");
    status.textContent = "Free Starter applies to one Chapter One draft with up to five selected sections. Revision, compliance and DOCX export require paid access.";
  } else {
    status.textContent = "Unlock this chapter for one draft, one revision, one compliance check and one DOCX export.";
  }
}

async function restoreCurrentProject() {
  const saved = currentProjectId || localStorage.getItem(CURRENT_PROJECT_STORAGE_KEY);
  if (!saved) return;
  try {
    const project = await api(`/api/projects/${saved}`);
    currentProjectId = project.id;
    localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, project.id);
    const profile = project.profile || {};
    if ($("title")) $("title").value = project.title || profile.title || "";
    if ($("level") && profile.level) $("level").value = profile.level;
    if ($("thesis_format") && profile.thesis_format) $("thesis_format").value = profile.thesis_format;
    if ($("research_area")) $("research_area").value = profile.research_area || "";
    if ($("study_context")) $("study_context").value = profile.study_context || "";
    if ($("projectStatus")) $("projectStatus").textContent = `Project restored: ${project.id}`;
  } catch (_) {
    localStorage.removeItem(CURRENT_PROJECT_STORAGE_KEY);
    currentProjectId = null;
  }
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
    updateLevelHint();
    updatePaymentPanel();
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
  box.querySelectorAll("input[name='section']").forEach(cb => cb.addEventListener("change", () => {
    renderAnswers();
    updatePaymentPanel();
  }));
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

function mergeSourceBank(existing, incoming, limit = 100) {
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
  localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, result.id);
  $("projectStatus").textContent = `Project created: ${result.id}`;
  updateChapterSpecificUi();
  await updatePaymentPanel();
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

function showDraftQualityHint(text, metrics = null) {
  const count = genericLanguageAudit(text);
  const status = $("draftStatus");
  if (!status) return;
  const metricText = metrics
    ? ` Estimated ${metrics.estimated_pages} pages from ${Number(metrics.word_count || 0).toLocaleString()} words, against a ${metrics.target_page_range}-page target. Citation density: ${metrics.citation_occurrences_per_1000_words} occurrences per 1,000 words.`
    : "";
  if (metrics && !metrics.depth_target_reached) {
    status.textContent = `Draft generated but remains below the planned depth target.${metricText} Add more verified evidence, results or source material, then revise or regenerate.`;
  } else if (count > 8) {
    status.textContent = `Draft generated.${metricText} Review generic transitions and add more project-specific evidence before final submission.`;
  } else {
    status.textContent = `Draft generated based on the information provided.${metricText} Review the evidence and revise before submission.`;
  }
}

async function generateDraft() {
  if (draftRequestInFlight) return;
  draftRequestInFlight = true;
  const draftButton = $("draftBtn");
  const originalButtonText = draftButton?.textContent || "Generate chapter draft";
  if (draftButton) {
    draftButton.disabled = true;
    draftButton.textContent = "Checking access...";
  }
  try {
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
    hideAccessRequiredNotice();
    $("draftOutput").value = result.draft;
  renderDraftPreview(result.draft);
  showDraftQualityHint(result.draft, result.generation_metrics || null);
  if (result.warning) {
    $("draftStatus").textContent = result.warning + " Review and complete the placeholders before export.";
  }
  $("downloadDraftBtn").disabled = false;
    await updatePaymentPanel();
  } finally {
    draftRequestInFlight = false;
    if (draftButton) {
      draftButton.disabled = false;
      draftButton.textContent = originalButtonText;
    }
  }
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
    max_results: $("sourceMaxResults") ? Number($("sourceMaxResults").value) : 30,
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

$("createProjectBtn").addEventListener("click", () => createProject().catch(err => handleWorkspaceError(err, "projectStatus")));
$("draftBtn").addEventListener("click", () => generateDraft().catch(err => handleWorkspaceError(err, "draftStatus")));
if ($("uploadResultsBtn")) $("uploadResultsBtn").addEventListener("click", () => uploadResults().catch(err => handleWorkspaceError(err, "uploadStatus")));
if ($("uploadRevisionBtn")) $("uploadRevisionBtn").addEventListener("click", () => uploadRevision().catch(err => handleWorkspaceError(err, "revisionStatus")));
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
  $("findSourcesBtn").addEventListener("click", () => findSources().catch(err => handleWorkspaceError(err, "sourceStatus")));
}
$("checkBtn").addEventListener("click", () => runCheck().then(updatePaymentPanel).catch(err => handleWorkspaceError(err, "draftStatus")));
$("downloadDraftBtn").addEventListener("click", () => {
  protectedDownload(`/api/projects/${currentProjectId}/export/chapter/${currentChapter}`, currentChapter)
    .then(updatePaymentPanel)
    .catch(err => handleWorkspaceError(err, "draftStatus"));
});
$("downloadCheckBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/check/${currentChapter}`));
if ($("unlockChapterBtn")) $("unlockChapterBtn").addEventListener("click", () => openCurrentCheckout().catch(err => handleWorkspaceError(err, "chapterAccessStatus")));
if ($("accessPayBtn")) $("accessPayBtn").addEventListener("click", () => openCurrentCheckout({direct: true}).catch(err => handleWorkspaceError(err, "draftStatus")));
if ($("accessDismissBtn")) $("accessDismissBtn").addEventListener("click", hideAccessRequiredNotice);
if ($("revisionMode")) $("revisionMode").addEventListener("change", updatePaymentPanel);
if ($("level")) {
  $("level").addEventListener("change", () => { updateLevelHint(); updatePaymentPanel(); });
  updateLevelHint();
}

updateChapterSpecificUi();

async function initialiseWorkspace() {
  const params = new URLSearchParams(window.location.search);
  const returnedProject = params.get("project_id");
  if (returnedProject) {
    currentProjectId = returnedProject;
    localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, returnedProject);
  }
  await loadTemplate();
  await restoreCurrentProject();
  const returnedChapter = Number(params.get("chapter") || 0);
  if (returnedChapter && $("chapterSelect")?.querySelector(`option[value="${returnedChapter}"]`)) {
    $("chapterSelect").value = String(returnedChapter);
    currentChapter = returnedChapter;
    renderSections();
  }
  const payment = params.get("payment");
  const registered = params.get("registered");
  if (registered === "1" && $("planNotice")) {
    $("planNotice").hidden = false;
    $("planNotice").textContent = "Registration profile saved. You can now continue with chapter access or payment.";
  }
  if (payment === "success") {
    if ($("planNotice")) {
      $("planNotice").hidden = false;
      $("planNotice").textContent = "Payment confirmed. Your chapter access is ready.";
    }
  } else if (payment === "failed") {
    if ($("planNotice")) {
      $("planNotice").hidden = false;
      $("planNotice").textContent = "Payment could not be confirmed. No chapter access was used.";
    }
  } else if (payment === "cancelled") {
    if ($("planNotice")) {
      $("planNotice").hidden = false;
      $("planNotice").textContent = "Checkout was cancelled. You can restart it when ready.";
    }
  }
  if (payment || registered) history.replaceState({}, document.title, window.location.pathname);
  await updatePaymentPanel();
}

initialiseWorkspace().catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});

