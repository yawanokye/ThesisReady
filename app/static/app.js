let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];
let latestSourceSearchResult = null;
let accumulatedSourceBank = [];
let uploadedRevisionText = "";
let uploadedRevisionFilename = "";
let alignmentUploadAttached = false;
let savedProjectDrafts = {};
let draftRequestInFlight = false;

const $ = (id) => document.getElementById(id);

const APP_STATIC_VERSION = "20260709-payment-resume-target-pages-v1";
const CURRENT_PROJECT_STORAGE_KEY = "projectready-current-project";
const WORKSPACE_SNAPSHOT_PREFIX = "projectready-workspace-snapshot:";
const PENDING_WORKSPACE_ACTION_KEY = "projectready-pending-workspace-action";


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

function parsePageRange(value) {
  const match = String(value || "").replace(/–/g, "-").match(/(\d+)\s*-\s*(\d+)/);
  if (!match) return {minimum: 8, maximum: 20};
  return {minimum: Number(match[1]), maximum: Number(match[2])};
}

function defaultPageRangeFor(level, chapter) {
  return parsePageRange(chapterPageTargets[level]?.[Number(chapter)] || "8-20");
}

function chapterTargetSettings() {
  const level = $("level")?.value || "Bachelors";
  const defaults = defaultPageRangeFor(level, currentChapter);
  const mode = $("targetPageMode")?.value || "default";
  let minimum = Number($("targetPageMin")?.value || defaults.minimum);
  let maximum = Number($("targetPageMax")?.value || defaults.maximum);
  if (!Number.isFinite(minimum) || minimum < 1) minimum = defaults.minimum;
  if (!Number.isFinite(maximum) || maximum < minimum) maximum = Math.max(minimum, defaults.maximum);
  return {
    mode,
    is_custom: mode === "custom",
    minimum_pages: minimum,
    maximum_pages: maximum,
    default_minimum_pages: defaults.minimum,
    default_maximum_pages: defaults.maximum,
    chapter_number: Number(currentChapter || 1),
    note: $("targetPageNote") ? $("targetPageNote").value.trim() : ""
  };
}

function updateLongChapterPlanPreview() {
  const box = $("longChapterPlanPreview");
  if (!box) return;
  const level = $("level")?.value || "Bachelors";
  const chapter = Number(currentChapter || 1);
  const settings = chapterTargetSettings();
  const midpointPages = (Number(settings.minimum_pages) + Number(settings.maximum_pages)) / 2;
  const targetWords = Math.round(midpointPages * 350 / 100) * 100;
  const doctoral = /PhD|Doctorate|DBA|DEd/i.test(level);
  const longMode = targetWords >= 9000 || (doctoral && chapter === 2);
  const units = Math.max(2, Math.min(18, Math.ceil(Math.max(targetWords, 1) / 2500)));
  if (!longMode) {
    box.innerHTML = `
      <strong>Standard chapter development</strong>
      <span>The selected target is about ${settings.minimum_pages}-${settings.maximum_pages} pages. The app will develop the selected sections in one guided pass, then report estimated pages and citation density.</span>
    `;
    return;
  }
  const litPlan = chapter === 2
    ? "chapter map → conceptual review → theory review → empirical review by objective → methodological review → contextual synthesis → contradictions and gaps → conceptual framework → coherence pass"
    : "chapter map → section batching → evidence and placeholder pass → coherence pass";
  box.innerHTML = `
    <strong>Staged long-chapter development is active</strong>
    <span>Target: about ${settings.minimum_pages}-${settings.maximum_pages} pages, roughly ${targetWords.toLocaleString()} planning words. The backend will split selected sections into about ${units} evidence-led development unit(s), then merge them into one coherent chapter.</span>
    <span class="long-plan-flow">${litPlan}</span>
  `;
}

function updateChapterTargetControls() {
  const mode = $("targetPageMode");
  const minInput = $("targetPageMin");
  const maxInput = $("targetPageMax");
  const summary = $("chapterTargetSummary");
  if (!mode || !minInput || !maxInput) return;
  const level = $("level")?.value || "Bachelors";
  const defaults = defaultPageRangeFor(level, currentChapter);
  if (mode.value !== "custom") {
    minInput.value = defaults.minimum;
    maxInput.value = defaults.maximum;
    minInput.disabled = true;
    maxInput.disabled = true;
  } else {
    minInput.disabled = false;
    maxInput.disabled = false;
    if (!minInput.value) minInput.value = defaults.minimum;
    if (!maxInput.value) maxInput.value = defaults.maximum;
  }
  const settings = chapterTargetSettings();
  if (summary) {
    summary.textContent = settings.is_custom
      ? `Custom target for Chapter ${currentChapter}: about ${settings.minimum_pages}-${settings.maximum_pages} pages. The model will treat this as a planning depth range, not filler.`
      : `Default ${level} target for Chapter ${currentChapter}: about ${settings.minimum_pages}-${settings.maximum_pages} pages. Select custom if the school or supervisor requires a different range.`;
  }
  updateLongChapterPlanPreview();
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

function workspaceReturnPath(extra = {}) {
  const url = new URL("/workspace", window.location.origin);
  if (currentProjectId) url.searchParams.set("project_id", currentProjectId);
  if (currentChapter) url.searchParams.set("chapter", String(currentChapter));
  const pending = readPendingWorkspaceAction();
  if (pending?.action) url.searchParams.set("resume", pending.action);
  Object.entries(extra || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) url.searchParams.set(key, String(value));
  });
  return url.pathname + url.search;
}

function currentAccessOptions() {
  return {
    projectId: currentProjectId,
    chapterNumber: Number(currentChapter),
    chapterTitle: currentChapterTitle(),
    academicLevel: $("level")?.value || "Bachelors",
    returnPath: workspaceReturnPath()
  };
}

function snapshotKey(projectId = currentProjectId) {
  const id = projectId || localStorage.getItem(CURRENT_PROJECT_STORAGE_KEY) || "unsaved";
  return `${WORKSPACE_SNAPSHOT_PREFIX}${id}`;
}

function readPendingWorkspaceAction() {
  try {
    const pending = JSON.parse(localStorage.getItem(PENDING_WORKSPACE_ACTION_KEY) || "null");
    return pending && typeof pending === "object" ? pending : null;
  } catch (_) {
    return null;
  }
}

function setPendingWorkspaceAction(action, details = {}) {
  if (!action) {
    localStorage.removeItem(PENDING_WORKSPACE_ACTION_KEY);
    return;
  }
  localStorage.setItem(PENDING_WORKSPACE_ACTION_KEY, JSON.stringify({
    action,
    project_id: currentProjectId || "",
    chapter_number: Number(currentChapter || 1),
    created_at: new Date().toISOString(),
    ...details
  }));
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value || ""));
  return String(value || "").replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function collectAnswerTextareas() {
  return Array.from(document.querySelectorAll("#answersBox textarea")).map(area => ({
    section: area.dataset.section || "",
    question: area.dataset.question || "",
    value: area.value || ""
  }));
}

function saveWorkspaceSnapshot(options = {}) {
  const fields = {};
  document.querySelectorAll("input[id], textarea[id], select[id]").forEach(el => {
    if (!el.id || el.type === "file" || el.type === "password") return;
    if (el.type === "checkbox") fields[el.id] = Boolean(el.checked);
    else fields[el.id] = el.value ?? "";
  });
  const snapshot = {
    version: APP_STATIC_VERSION,
    project_id: currentProjectId || localStorage.getItem(CURRENT_PROJECT_STORAGE_KEY) || "",
    chapter_number: Number(currentChapter || 1),
    selected_section_ids: selectedSectionIds(),
    answer_textareas: collectAnswerTextareas(),
    fields,
    latest_source_search_result: latestSourceSearchResult,
    accumulated_source_bank: accumulatedSourceBank,
    uploaded_revision_text: uploadedRevisionText ? uploadedRevisionText.slice(0, 250000) : "",
    uploaded_revision_filename: uploadedRevisionFilename || "",
    alignment_upload_attached: Boolean(alignmentUploadAttached),
    saved_project_drafts: savedProjectDrafts || {},
    previous_chapter_status: $("previousChapterStatus")?.textContent || "",
    previous_chapter_preview: $("previousChapterPreview")?.textContent || "",
    revision_status: $("revisionStatus")?.textContent || "",
    revision_preview: $("revisionPreview")?.textContent || "",
    upload_status: $("uploadStatus")?.textContent || "",
    upload_preview: $("uploadPreview")?.textContent || "",
    draft_output: $("draftOutput")?.value || "",
    draft_status: $("draftStatus")?.textContent || "",
    saved_at: new Date().toISOString(),
    reason: options.reason || "workspace_state"
  };
  try {
    const key = snapshotKey(snapshot.project_id || currentProjectId);
    localStorage.setItem(key, JSON.stringify(snapshot));
    if (snapshot.project_id) localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, snapshot.project_id);
  } catch (error) {
    console.warn("ProjectReady workspace snapshot could not be saved", error);
  }
  return snapshot;
}

function restoreWorkspaceSnapshot(projectId = currentProjectId, options = {}) {
  let snapshot = null;
  try {
    snapshot = JSON.parse(localStorage.getItem(snapshotKey(projectId)) || "null");
  } catch (_) {
    snapshot = null;
  }
  if (!snapshot || typeof snapshot !== "object") return null;
  const fields = snapshot.fields || {};
  const targetChapter = Number(options.preferredChapter || snapshot.chapter_number || currentChapter || 1);
  if ($("chapterSelect") && targetChapter && $("chapterSelect").querySelector(`option[value="${targetChapter}"]`)) {
    $("chapterSelect").value = String(targetChapter);
    currentChapter = targetChapter;
    renderSections();
  }
  Object.entries(fields).forEach(([id, value]) => {
    if (id === "chapterSelect" || id === "recoveryPin") return;
    const el = $(id);
    if (!el || el.type === "file" || el.type === "password") return;
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = String(value ?? "");
  });
  if (Array.isArray(snapshot.selected_section_ids) && snapshot.selected_section_ids.length) {
    const selected = new Set(snapshot.selected_section_ids.map(String));
    document.querySelectorAll("input[name='section']").forEach(cb => { cb.checked = selected.has(cb.value); });
    renderAnswers();
  }
  if (Array.isArray(snapshot.answer_textareas)) {
    snapshot.answer_textareas.forEach(item => {
      const area = document.querySelector(`#answersBox textarea[data-section="${cssEscape(item.section || "")}"][data-question="${cssEscape(item.question || "")}"]`);
      if (area) area.value = item.value || "";
    });
  }
  latestSourceSearchResult = snapshot.latest_source_search_result || latestSourceSearchResult;
  accumulatedSourceBank = Array.isArray(snapshot.accumulated_source_bank) ? snapshot.accumulated_source_bank : accumulatedSourceBank;
  uploadedRevisionText = snapshot.uploaded_revision_text || uploadedRevisionText || "";
  uploadedRevisionFilename = snapshot.uploaded_revision_filename || uploadedRevisionFilename || "";
  alignmentUploadAttached = Boolean(snapshot.alignment_upload_attached || alignmentUploadAttached);
  savedProjectDrafts = snapshot.saved_project_drafts || savedProjectDrafts || {};
  if ($("previousChapterStatus") && snapshot.previous_chapter_status) $("previousChapterStatus").textContent = snapshot.previous_chapter_status;
  if ($("previousChapterPreview") && snapshot.previous_chapter_preview) $("previousChapterPreview").textContent = snapshot.previous_chapter_preview;
  if ($("revisionStatus") && snapshot.revision_status) $("revisionStatus").textContent = snapshot.revision_status;
  if ($("revisionPreview") && snapshot.revision_preview) $("revisionPreview").textContent = snapshot.revision_preview;
  if ($("uploadStatus") && snapshot.upload_status) $("uploadStatus").textContent = snapshot.upload_status;
  if ($("uploadPreview") && snapshot.upload_preview) $("uploadPreview").textContent = snapshot.upload_preview;
  if ($("draftOutput") && snapshot.draft_output) {
    $("draftOutput").value = snapshot.draft_output;
    renderDraftPreview(snapshot.draft_output);
    if ($("downloadDraftBtn")) $("downloadDraftBtn").disabled = false;
  }
  updateChapterSpecificUi();
  updateLevelHint();
  updateChapterTargetControls();
  return snapshot;
}

window.ProjectReadyWorkspace = {
  saveSnapshot: saveWorkspaceSnapshot,
  restoreSnapshot: restoreWorkspaceSnapshot,
  setPendingAction: setPendingWorkspaceAction,
  readPendingAction: readPendingWorkspaceAction
};

function hideAccessRequiredNotice() {
  const notice = $("accessRequiredNotice");
  if (notice) notice.hidden = true;
}

function showAccessRequiredNotice(error) {
  const notice = $("accessRequiredNotice");
  const message = $("accessRequiredMessage");
  const registerLink = $("accessRegisterBtn");
  if (!notice) return;
  const detailMessage = error?.detail?.message || error?.message || "Register or unlock guided chapter development to continue.";
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
  saveWorkspaceSnapshot({reason: "before_checkout"});
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
        status.textContent = `Payment confirmed. Remaining guided draft: ${r.draft ?? 0}, strengthening revision: ${r.revision ?? 0}, compliance review: ${r.compliance ?? 0}, export: ${r.export ?? 0}.`;
        button.textContent = "Purchase another guided chapter access";
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

  button.textContent = "Unlock guided chapter development";
  if (freeEligible) {
    panel.classList.add("is-warning");
    status.textContent = "Free Starter applies to one limited Chapter One working draft with up to five selected sections. Strengthening, compliance review and DOCX export require paid access.";
  } else {
    status.textContent = "Unlock guided chapter development for one working draft, one strengthening revision, one compliance review and one editable DOCX export.";
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
    if ($("format_notes")) $("format_notes").value = profile.format_notes || "";
    if ($("citation_evidence_notes")) $("citation_evidence_notes").value = profile.citation_evidence_notes || "";
    if ($("research_approach") && profile.research_approach) $("research_approach").value = profile.research_approach;
    if ($("data_type") && profile.data_type) $("data_type").value = profile.data_type;
    const storedTarget = (profile.chapter_page_targets || {})[String(currentChapter || 1)] || profile.current_chapter_page_target || null;
    if (storedTarget && $("targetPageMode")) {
      $("targetPageMode").value = storedTarget.is_custom || storedTarget.mode === "custom" ? "custom" : "default";
      if ($("targetPageMin") && storedTarget.minimum_pages) $("targetPageMin").value = storedTarget.minimum_pages;
      if ($("targetPageMax") && storedTarget.maximum_pages) $("targetPageMax").value = storedTarget.maximum_pages;
      if ($("targetPageNote") && storedTarget.note) $("targetPageNote").value = storedTarget.note;
    }
    if ($("objectives") && Array.isArray(profile.objectives)) $("objectives").value = profile.objectives.join("\n");
    if ($("variables_constructs") && profile.variables?.raw_variables) $("variables_constructs").value = profile.variables.raw_variables.join("\n");
    applyAlignmentProfile(profile.chapter_one_alignment_profile || {});
    if ($("academicIntegrityDeclaration")) $("academicIntegrityDeclaration").checked = Boolean(profile.academic_integrity_confirmed);
    if ($("userContributionDeclaration")) $("userContributionDeclaration").checked = Boolean(profile.user_contribution_confirmed);
    const alignmentUploads = profile.uploaded_alignment_chapters || {};
    const alignmentCount = Array.isArray(alignmentUploads) ? alignmentUploads.length : Object.keys(alignmentUploads || {}).length;
    savedProjectDrafts = project.drafts || {};
    alignmentUploadAttached = alignmentCount > 0;
    if ($("previousChapterStatus") && alignmentCount) {
      $("previousChapterStatus").textContent = `${alignmentCount} previous-chapter/full-work alignment upload(s) are already attached to this project.`;
    }
    if ($("saveRecoveryBtn")) $("saveRecoveryBtn").disabled = false;
    if ($("projectStatus")) $("projectStatus").textContent = project.recovery_enabled
      ? `Project restored: ${project.id}. Recovery is enabled.`
      : `Project restored: ${project.id}. Add a recovery email and PIN to make the ID recoverable.`;
  } catch (_) {
    localStorage.removeItem(CURRENT_PROJECT_STORAGE_KEY);
    currentProjectId = null;
  }
}


function lines(value) {
  return (value || "").split("\n").map(v => v.trim()).filter(Boolean);
}

function fillIfBlank(id, value) {
  const el = $(id);
  if (!el || el.value.trim() || value === undefined || value === null) return false;
  if (Array.isArray(value)) {
    if (!value.length) return false;
    el.value = value.join("\n");
  } else {
    const text = String(value || "").trim();
    if (!text) return false;
    el.value = text;
  }
  return true;
}

function applyAlignmentProfile(profile = {}) {
  if (!profile || typeof profile !== "object") return 0;
  let applied = 0;
  if (fillIfBlank("study_context", profile.study_context)) applied += 1;
  if (fillIfBlank("objectives", profile.objectives)) applied += 1;
  if (fillIfBlank("variables_constructs", profile.variables_constructs)) applied += 1;
  if (fillIfBlank("centralArgument", profile.problem_extract || profile.theory_framework_extract)) applied += 1;
  const rqBox = document.querySelector("#answersBox textarea");
  if (rqBox && !rqBox.value.trim() && Array.isArray(profile.research_questions) && profile.research_questions.length) {
    rqBox.value = profile.research_questions.join("\n");
    applied += 1;
  }
  return applied;
}

function chapterOneContextAvailable() {
  return Boolean(alignmentUploadAttached || hasSavedEarlierDraftForAlignment() || ($("previousChaptersContext")?.value.trim().length || 0) >= 80);
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
  const previousBox = $("previousChaptersBox");
  if (previousBox) previousBox.hidden = false;
  const previousSelect = $("previousChapterNumber");
  const target = Math.max(2, Number(currentChapter || 1));
  if (previousSelect) {
    const selected = Number(previousSelect.value || 1);
    if (target > 1 && selected !== 0 && selected >= target) {
      previousSelect.value = String(Math.max(1, target - 1));
    }
  }
  const uploadTitle = $("previousChaptersTitle");
  if (uploadTitle) uploadTitle.textContent = target <= 2
    ? "Upload Chapter One or introduction for auto-fill and alignment"
    : "Upload earlier chapters or full work for alignment checks";
  const uploadHint = $("previousChaptersHint");
  if (uploadHint) uploadHint.textContent = target <= 2
    ? "Upload the approved Chapter One/introduction once. The workspace will extract the study context, objectives, questions, variables and problem background where possible, then use the file for Chapter Two alignment. Add extra notes only when the uploaded chapter does not contain enough detail."
    : "Upload the earlier chapter(s) or the complete existing work so the active chapter can stay aligned with the title, problem, objectives, questions, hypotheses, theory, variables, terminology and methods.";
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
              "Which parts are intended only for the appendix or research preparation, rather than the main methodology working draft?"
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
    updateChapterTargetControls();
    saveWorkspaceSnapshot({reason: "chapter_changed"});
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
  updateChapterTargetControls();
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
    project_kind: "standard",
    recovery_email: $("recoveryEmail") ? $("recoveryEmail").value.trim() : "",
    recovery_pin: $("recoveryPin") ? $("recoveryPin").value.trim() : "",
    academic_integrity_confirmed: $("academicIntegrityDeclaration") ? $("academicIntegrityDeclaration").checked : false,
    user_contribution_confirmed: $("userContributionDeclaration") ? $("userContributionDeclaration").checked : false,
    allow_provisional_drafting: true,
    programme: "",
    department: "",
    institution: "",
    level: selectedLevel,
    academic_level_guidance: levelDepthGuidance[selectedLevel] || "",
    chapter_page_targets: {[String(currentChapter || 1)]: chapterTargetSettings()},
    current_chapter_page_target: chapterTargetSettings(),
    long_chapter_workflow_visible: true,
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


function hasSavedEarlierDraftForAlignment() {
  const target = Number(currentChapter || 1);
  if (!savedProjectDrafts || target <= 1) return false;
  return Object.entries(savedProjectDrafts).some(([numberText, draft]) => {
    const number = Number(numberText);
    return number > 0 && number < target && String(draft || "").trim().length >= 80;
  });
}

function responsibleUseConfirmed() {
  return Boolean(
    $("academicIntegrityDeclaration")?.checked
    && $("userContributionDeclaration")?.checked
  );
}

function ownInputReadinessProblems({revisionMode = false} = {}) {
  const problems = [];
  if (!responsibleUseConfirmed()) {
    problems.push("confirm both academic-integrity and user-contribution declarations");
  }
  if (revisionMode) {
    if (!uploadedRevisionText.trim() && !$('draftOutput')?.value.trim()) {
      problems.push("upload or load the existing chapter that you want to strengthen");
    }
    return problems;
  }
  if (!selectedSectionIds().length) problems.push("select at least one required chapter section");
  return problems;
}

function draftConsiderationWarnings({revisionMode = false} = {}) {
  if (revisionMode) return [];
  const warnings = [];
  const context = $('study_context')?.value.trim() || "";
  const area = $('research_area')?.value.trim() || "";
  const objectives = lines($('objectives')?.value || "");
  const answers = collectAnswers();
  const answerText = Object.values(answers).flatMap(section => Object.values(section || {})).join(" ");
  const contributionValues = [
    $('centralArgument')?.value.trim() || "",
    $('localContextNotes')?.value.trim() || "",
    $('evidenceAnchors')?.value.trim() || "",
    $('citation_evidence_notes')?.value.trim() || "",
    $('format_notes')?.value.trim() || "",
    $('supervisorComments')?.value.trim() || "",
  ];
  const contributionText = contributionValues.join(" ").trim();
  const hasChapterOneContext = chapterOneContextAvailable();
  if (!hasChapterOneContext) {
    if (!area && context.length < 30) warnings.push("research area and study context are limited");
    if (!objectives.length && answerText.length < 60) warnings.push("objectives, research questions or guided-section answers are limited");
    if (contributionText.length < 140) warnings.push("evidence, argument, context or supervisor direction is limited");
  }
  if (Number(currentChapter || 1) >= 2 && !hasChapterOneContext) {
    warnings.push("earlier chapter alignment context has not been supplied, so the draft will include alignment-confirmation placeholders");
  }
  return warnings;
}


async function createProject() {
  const profile = collectProfile();
  if (!profile.title) {
    $("projectStatus").textContent = "Please enter your approved or provisional research title.";
    return null;
  }
  if (!responsibleUseConfirmed()) {
    $("projectStatus").textContent = "Confirm both academic-integrity and user-contribution declarations before creating the research project.";
    $("academicIntegrityPanel")?.scrollIntoView({behavior: "smooth", block: "center"});
    return null;
  }
  if ((profile.recovery_email && !/^\d{6}$/.test(profile.recovery_pin)) || (!profile.recovery_email && profile.recovery_pin)) {
    $("projectStatus").textContent = "Provide both a valid recovery email and a 6-digit recovery PIN, or leave both blank.";
    return null;
  }
  $("projectStatus").textContent = "Creating research project...";
  const result = await api("/api/projects", { method: "POST", body: JSON.stringify(profile) });
  currentProjectId = result.id;
  localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, result.id);
  if ($("saveRecoveryBtn")) $("saveRecoveryBtn").disabled = false;
  $("projectStatus").textContent = result.recovery_enabled
    ? `Project created: ${result.id}. Recovery is enabled for the saved email and PIN.`
    : `Project created: ${result.id}. Add a recovery email and PIN to protect access if the ID is lost.`;
  updateChapterSpecificUi();
  updateChapterTargetControls();
  saveWorkspaceSnapshot({reason: "project_created"});
  await updatePaymentPanel();
  return result.id;
}

async function saveCurrentProjectRecovery() {
  if (!currentProjectId) throw new Error("Create or restore a project first.");
  const email = $("recoveryEmail")?.value.trim() || "";
  const recoveryPin = $("recoveryPin")?.value.trim() || "";
  if (!email || !/^\d{6}$/.test(recoveryPin)) {
    throw new Error("Enter a valid recovery email and a 6-digit recovery PIN.");
  }
  const result = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/recovery`, {
    method: "POST",
    body: JSON.stringify({email, recovery_pin: recoveryPin})
  });
  $("projectStatus").textContent = result.message || "Project recovery enabled.";
  return result;
}

async function recoverWorkspaceProjects() {
  const results = $("workspaceRecoveryResults");
  const email = $("recoveryEmail")?.value.trim() || "";
  const recoveryPin = $("recoveryPin")?.value.trim() || "";
  if (results) results.textContent = "Checking recovery details...";
  const response = await fetch("/api/projects/recover", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({email, recovery_pin: recoveryPin})
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "No project matched those recovery details.");
  for (const credential of data.restored_access || []) {
    window.ProjectReadyPayments?.saveCredential?.(
      credential.project_id,
      credential.chapter_number,
      credential
    );
  }
  if (!results) return data;
  results.innerHTML = "";
  for (const project of data.projects || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-action recovered-project-button";
    button.textContent = `${project.title} · ${project.academic_level || "Level not set"} · ${project.id}`;
    button.addEventListener("click", async () => {
      currentProjectId = project.id;
      localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, project.id);
      await restoreCurrentProject();
      await updatePaymentPanel();
    });
    results.appendChild(button);
  }
  return data;
}

function prefillRecoveryEmail() {
  if (!$("recoveryEmail") || $("recoveryEmail").value) return;
  const profile = window.ProjectReadyPayments?.readRegistrationProfile?.();
  if (profile?.email) $("recoveryEmail").value = profile.email;
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
  const longModeText = metrics?.long_chapter_strategy?.enabled ? " Staged long-chapter mode was used for planning and section batching." : "";
  const metricText = metrics
    ? ` Estimated ${metrics.estimated_pages} pages from ${Number(metrics.word_count || 0).toLocaleString()} words, against a ${metrics.target_page_range}-page target. Citation density: ${metrics.citation_occurrences_per_1000_words} occurrences per 1,000 words.${longModeText}`
    : "";
  if (metrics && !metrics.depth_target_reached) {
    status.textContent = `Working draft developed but remains below the planned depth target.${metricText} Add more verified evidence, results or source material, then revise or regenerate.`;
  } else if (count > 8) {
    status.textContent = `Working draft developed.${metricText} Review generic transitions and add more project-specific evidence before any submission.`;
  } else {
    status.textContent = `Working draft developed from the information you supplied.${metricText} Review every source, fact and argument, then revise before any submission.`;
  }
}

async function generateDraft() {
  if (draftRequestInFlight) return;
  draftRequestInFlight = true;
  const draftButton = $("draftBtn");
  const originalButtonText = draftButton?.textContent || "Develop working draft";
  if (draftButton) {
    draftButton.disabled = true;
    draftButton.textContent = "Checking access...";
  }
  try {
    if (!currentProjectId) await createProject();
    if (!currentProjectId) return;
    const revisionMode = $("revisionMode") ? $("revisionMode").checked : false;
    const readinessProblems = ownInputReadinessProblems({revisionMode});
    if (readinessProblems.length) {
      $("draftStatus").textContent = `Complete the required responsibility checks before continuing: ${readinessProblems.join("; ")}.`;
      return;
    }
    const considerationWarnings = draftConsiderationWarnings({revisionMode});
    const profileSnapshot = collectProfile();
    profileSnapshot.draft_consideration_warnings = considerationWarnings;
    delete profileSnapshot.recovery_pin;
    delete profileSnapshot.recovery_email;
    setPendingWorkspaceAction("draft", {revision_mode: revisionMode});
    saveWorkspaceSnapshot({reason: "before_draft_request"});
    const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    answers: collectAnswers(),
    extra_instructions: $("extraInstructions").value.trim(),
    use_ai: $("useAi") ? $("useAi").checked : true,
    revision_mode: revisionMode,
    revision_instructions: $("revisionInstructions") ? $("revisionInstructions").value.trim() : "",
    revision_text: uploadedRevisionText,
    revision_filename: uploadedRevisionFilename,
    previous_chapters_context: $("previousChaptersContext") ? $("previousChaptersContext").value.trim() : "",
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
    academic_integrity_confirmed: $("academicIntegrityDeclaration") ? $("academicIntegrityDeclaration").checked : false,
    user_contribution_confirmed: $("userContributionDeclaration") ? $("userContributionDeclaration").checked : false,
    draft_consideration_warnings: considerationWarnings,
    allow_provisional_drafting: true,
    profile_updates: profileSnapshot,
    ...currentSourcePayload()
  };
  if (revisionMode) {
    $("draftStatus").textContent = "Strengthening your existing chapter...";
  } else if (considerationWarnings.length) {
    $("draftStatus").textContent = `Developing a provisional working draft for consideration. Missing or limited inputs will be marked with placeholders: ${considerationWarnings.join("; ")}.`;
  } else if (chapterOneContextAvailable() && Number(currentChapter || 1) >= 2) {
    $("draftStatus").textContent = "Developing the working draft using the uploaded Chapter One or earlier-chapter alignment profile...";
  } else {
    $("draftStatus").textContent = "Developing the working draft from your research inputs...";
  }
    let result;
    try {
      result = await api(`/api/projects/${currentProjectId}/draft`, { method: "POST", body: JSON.stringify(payload) });
    } catch (error) {
      if (![401, 402].includes(Number(error.status))) setPendingWorkspaceAction(null);
      throw error;
    }
    hideAccessRequiredNotice();
    setPendingWorkspaceAction(null);
    $("draftOutput").value = result.draft;
    savedProjectDrafts[String(currentChapter)] = result.draft || "";
    renderDraftPreview(result.draft);
    showDraftQualityHint(result.draft, result.generation_metrics || null);
    if (result.warning) {
      $("draftStatus").textContent = result.warning + " Review the working draft and complete every placeholder before export.";
    }
    $("downloadDraftBtn").disabled = false;
    saveWorkspaceSnapshot({reason: "draft_completed"});
    await updatePaymentPanel();
  } finally {
    draftRequestInFlight = false;
    if (draftButton) {
      draftButton.disabled = false;
      draftButton.textContent = originalButtonText;
    }
  }
}


async function uploadPreviousChapterForAlignment() {
  if (!currentProjectId) await createProject();
  const input = $("previousChapterFile");
  if (!input || !input.files || input.files.length === 0) {
    $("previousChapterStatus").textContent = "Please select an earlier chapter or complete-work file first.";
    return;
  }
  const targetChapter = Math.max(2, Number(currentChapter || 1));
  const sourceNumber = Number($("previousChapterNumber")?.value || 1);
  if (sourceNumber !== 0 && sourceNumber >= targetChapter) {
    $("previousChapterStatus").textContent = "Choose an earlier source chapter, or choose complete existing work / full thesis.";
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);
  formData.append("source_chapter_number", String(sourceNumber));
  formData.append("target_chapter_number", String(targetChapter));

  $("previousChapterStatus").textContent = "Uploading, extracting and preparing the alignment profile...";
  const response = await fetch(`/api/projects/${currentProjectId}/upload-alignment-chapter`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const result = await response.json();
  alignmentUploadAttached = true;
  const appliedCount = applyAlignmentProfile(result.alignment_profile || {});
  const appliedNote = appliedCount ? ` Auto-filled ${appliedCount} project field(s) from the upload. Review and edit them where needed.` : " The upload will be used for alignment checks.";
  $("previousChapterStatus").textContent = (result.message || `Uploaded ${result.filename} for Chapter ${result.target_chapter_number} alignment checks.`) + appliedNote;
  $("previousChapterPreview").textContent = result.preview || "No preview available.";
  saveWorkspaceSnapshot({reason: "alignment_upload"});
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
  saveWorkspaceSnapshot({reason: "results_upload"});
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
  saveWorkspaceSnapshot({reason: "revision_upload"});
}


async function findSources() {
  if (!currentProjectId) await createProject();
  const payload = {
    query: $("sourceSearchQuery") ? $("sourceSearchQuery").value.trim() : "",
    max_results: $("sourceMaxResults") ? Number($("sourceMaxResults").value) : 30,
    include_older_foundational: $("includeOlderFoundational") ? $("includeOlderFoundational").checked : true,
    use_relevance_gate: true,
    attach_not_relevant_sources: false
  };
  $("sourceStatus").textContent = "Searching scholarly sources and attaching them to the project...";
  const result = await api(`/api/projects/${currentProjectId}/find-sources`, { method: "POST", body: JSON.stringify(payload) });
  latestSourceSearchResult = result;
  // The backend replaces earlier automated search results after each refined
  // search. Mirror that behaviour locally so stale unrelated sources are not
  // sent back during drafting.
  accumulatedSourceBank = result.source_bank || result.sources || [];
  renderSources(result);
  saveWorkspaceSnapshot({reason: "source_search"});
  const errors = (result.provider_errors || []).length;
  const attached = result.attached_count_this_search ?? result.count ?? 0;
  const rejected = result.rejected_irrelevant_count || 0;
  const requested = result.requested_count || payload.max_results;
  $("sourceStatus").textContent = `Attached ${attached} relevant source(s) from a maximum of ${requested}. Rejected ${rejected} unrelated record(s). ${errors ? errors + " provider(s) could not be reached." : ""}`;
}

function renderSources(result) {
  const box = $("sourceResults");
  if (!box) return;
  const sources = result.sources || [];
  if (!sources.length) {
    box.innerHTML = `<p class="hint">No source records were found. Refine the search terms and try again.</p>`;
    return;
  }
  const relevance = result.relevance_summary || {};
  const requested = result.requested_count || sources.length;
  const meta = `
    <div class="source-meta">
      <strong>Search query:</strong> ${escapeHtml(result.query || "")}<br />
      <strong>Recent-reference window:</strong> ${escapeHtml(result.recent_reference_window || "")}<br />
      <strong>Databases searched:</strong> ${escapeHtml((result.databases || []).join(", "))}<br />
      <strong>Relevance gate:</strong> ${escapeHtml(relevance.highly_relevant || 0)} highly relevant, ${escapeHtml(relevance.partly_relevant || 0)} partly relevant, ${escapeHtml(relevance.not_attached_as_irrelevant || 0)} unrelated rejected.<br />
      <strong>Result rule:</strong> ${escapeHtml(sources.length)} attached from a requested maximum of ${escapeHtml(requested)}. The app no longer pads the list with unrelated papers.
    </div>`;
  const cards = sources.map((src, idx) => {
    const authors = Array.isArray(src.authors) ? src.authors.join(", ") : (src.authors || "");
    const doi = src.doi ? ` DOI: ${escapeHtml(src.doi)}` : "";
    const url = src.url ? `<a href="${escapeHtml(src.url)}" target="_blank" rel="noopener">Open source record</a>` : "";
    const abstract = src.abstract ? `<p>${escapeHtml(src.abstract)}</p>` : `<p class="hint">No abstract was returned by the metadata provider.</p>`;
    const tier = src.relevance_tier || "partly_relevant";
    const tierLabel = tier === "highly_relevant" ? "Highly relevant" : "Partly relevant";
    return `
      <div class="source-card">
        <div class="source-tier ${escapeHtml(tier)}">${escapeHtml(tierLabel)}</div>
        <div class="source-title">${idx + 1}. ${escapeHtml(src.title || "Untitled source")}</div>
        <div class="source-sub">${escapeHtml(authors)} ${src.year ? "(" + escapeHtml(src.year) + ")" : ""}</div>
        <div class="source-sub">${escapeHtml(src.source || src.database || "")} ${doi}</div>
        ${abstract}
        <div class="source-relevance"><strong>Why it matched:</strong> ${escapeHtml(src.relevance_reason || "Direct topic match identified.")}</div>
        <div class="source-relevance"><strong>Suggested use:</strong> ${escapeHtml(src.suggested_use || "Use only where it directly supports the claim.")}</div>
        <div class="source-hint"><strong>Citation hint:</strong> ${escapeHtml(src.apa_hint || "")}</div>
        <div class="source-link">${url}</div>
      </div>`;
  }).join("");
  box.innerHTML = meta + cards;
}

async function runCheck() {
  if (!currentProjectId) {
    $("draftStatus").textContent = "Create a research project and develop a working draft first.";
    return;
  }
  const payload = {
    chapter_number: currentChapter,
    selected_section_ids: selectedSectionIds(),
    draft: $("draftOutput").value
  };
  $("draftStatus").textContent = "Running the academic compliance review...";
  const result = await api(`/api/projects/${currentProjectId}/check`, { method: "POST", body: JSON.stringify(payload) });
  renderCheck(result);
  $("draftStatus").textContent = "Academic compliance review completed. This does not replace supervisor or institutional approval.";
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
if ($("saveRecoveryBtn")) $("saveRecoveryBtn").addEventListener("click", () => saveCurrentProjectRecovery().catch(err => handleWorkspaceError(err, "projectStatus")));
if ($("recoverProjectBtn")) $("recoverProjectBtn").addEventListener("click", () => recoverWorkspaceProjects().catch(err => handleWorkspaceError(err, "projectStatus")));
$("draftBtn").addEventListener("click", () => generateDraft().catch(err => handleWorkspaceError(err, "draftStatus")));
if ($("uploadPreviousChapterBtn")) $("uploadPreviousChapterBtn").addEventListener("click", () => uploadPreviousChapterForAlignment().catch(err => handleWorkspaceError(err, "previousChapterStatus")));
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
  $("level").addEventListener("change", () => {
    updateLevelHint();
    updateChapterTargetControls();
    saveWorkspaceSnapshot({reason: "level_changed"});
    updatePaymentPanel();
  });
  updateLevelHint();
}
["targetPageMode", "targetPageMin", "targetPageMax", "targetPageNote"].forEach(id => {
  const el = $(id);
  if (!el) return;
  el.addEventListener("input", () => { updateChapterTargetControls(); saveWorkspaceSnapshot({reason: "target_pages_changed"}); });
  el.addEventListener("change", () => { updateChapterTargetControls(); saveWorkspaceSnapshot({reason: "target_pages_changed"}); });
});

let workspaceSnapshotTimer = null;
document.addEventListener("input", event => {
  if (!event.target?.id || event.target.type === "password" || event.target.type === "file") return;
  clearTimeout(workspaceSnapshotTimer);
  workspaceSnapshotTimer = setTimeout(() => saveWorkspaceSnapshot({reason: "autosave"}), 600);
}, true);
document.addEventListener("change", event => {
  if (!event.target?.id || event.target.type === "password" || event.target.type === "file") return;
  saveWorkspaceSnapshot({reason: "autosave_change"});
}, true);

updateChapterSpecificUi();
updateChapterTargetControls();

async function initialiseWorkspace() {
  prefillRecoveryEmail();
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
  restoreWorkspaceSnapshot(currentProjectId, {preferredChapter: returnedChapter || currentChapter});
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
  await resumePendingDraftAfterPayment(payment, params.get("resume"));
}

async function resumePendingDraftAfterPayment(payment, resumeParam = "") {
  if (payment !== "success") return;
  const pending = readPendingWorkspaceAction();
  const resumeRequested = resumeParam === "draft" || pending?.action === "draft";
  if (!resumeRequested || !pending) return;
  if (pending.project_id && currentProjectId && pending.project_id !== currentProjectId) return;
  if (Number(pending.chapter_number || currentChapter) !== Number(currentChapter || 1)) return;
  if ($("draftStatus")) $("draftStatus").textContent = "Payment confirmed. Resuming the draft development with the information already entered.";
  try {
    await generateDraft();
  } catch (error) {
    await handleWorkspaceError(error, "draftStatus");
  }
}

initialiseWorkspace().catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});

