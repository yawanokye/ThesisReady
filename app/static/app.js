let template = null;
let currentProjectId = null;
let currentChapter = 1;
let currentSections = [];
let latestSourceSearchResult = null;
let accumulatedSourceBank = [];
let selectedPapers = [];
let uploadedRevisionText = "";
let uploadedRevisionFilename = "";
let alignmentUploadAttached = false;
let savedProjectDrafts = {};
let draftRequestInFlight = false;
let customPageTargets = {};
let activeBackgroundJob = null;
let currentContinuation = null;
let currentClaimSupportReview = null;

const $ = (id) => document.getElementById(id);

const APP_STATIC_VERSION = "20260815-selected-papers-v1";
const CURRENT_PROJECT_STORAGE_KEY = "projectready-current-project";

const WORKSPACE_NEW_JOB_PARAM = "new_job";


let workspaceAccessState = null;
let workspaceComplimentaryState = null;

function workspaceDefaultMaxPages() {
  const custom = currentPageTargetInput();
  if (custom.mode === "custom" && custom.maximum) return Number(custom.maximum);
  const level = $("level")?.value || "Bachelors";
  const range = String(chapterPageTargets[level]?.[Number(currentChapter || 1)] || "");
  const numbers = range.match(/\d+/g) || [];
  return Number(numbers[numbers.length - 1] || 0);
}

function workspaceFreeStarterEligible() {
  return Number(currentChapter || 1) === 1 && selectedSectionIds().length > 0 && selectedSectionIds().length <= 5 && !$("revisionMode")?.checked;
}

function workspaceHasPaidCredential() {
  return Boolean(window.ProjectReadyPayments?.getCredential?.(currentProjectId, currentChapter));
}

function setWorkspaceFlowStep(name, complete, current) {
  const node = document.querySelector(`#workspaceFlowSteps [data-flow-step="${name}"]`);
  if (!node) return;
  node.classList.toggle("complete", Boolean(complete));
  node.classList.toggle("current", Boolean(current));
}

function updateWorkspaceFlow() {
  const titleReady = Boolean($("title")?.value.trim());
  const projectReady = Boolean(currentProjectId && titleReady);
  const chapterReady = projectReady && selectedSectionIds().length > 0;
  const answers = Array.from(document.querySelectorAll("#questionsBox textarea, #questionsBox input[type='text']"));
  const detailsReady = chapterReady && (answers.length === 0 || answers.some(field => String(field.value || "").trim().length >= 3));
  const evidenceOptionalReady = detailsReady;
  const accessReady = Boolean(
    workspaceAccessState?.temporary_open ||
    workspaceComplimentaryState?.allowed ||
    workspaceHasPaidCredential() ||
    (workspaceAccessState?.free_starter_enabled && workspaceFreeStarterEligible())
  );
  const generated = Boolean($("draftOutput")?.value.trim() || savedProjectDrafts?.[String(currentChapter)] || savedProjectDrafts?.[currentChapter]);
  const reviewed = Boolean($("scoreBox")?.textContent.trim() || $("downloadCheckBtn")?.disabled === false);
  const states = [
    ["project", projectReady], ["chapter", chapterReady], ["details", detailsReady],
    ["evidence", evidenceOptionalReady], ["access", accessReady], ["generate", generated], ["review", reviewed]
  ];
  const firstIncomplete = states.find(([_, complete]) => !complete)?.[0] || "review";
  states.forEach(([name, complete]) => setWorkspaceFlowStep(name, complete, name === firstIncomplete));
  const completeCount = states.filter(([_, complete]) => complete).length;
  if ($("workspaceFlowSummary")) {
    const labels = {project:"Complete the project profile.",chapter:"Choose the chapter and sections.",details:"Add the chapter-specific details.",evidence:"Review evidence and alignment options.",access:"Confirm chapter access.",generate:"Develop the chapter working draft.",review:"Review, check and export the chapter."};
    $("workspaceFlowSummary").textContent = completeCount === states.length ? "Chapter workflow complete. You can continue to the next chapter." : `${completeCount} of ${states.length} steps complete. ${labels[firstIncomplete] || "Continue below."}`;
  }
}

function renderWorkspaceAccessStatus() {
  const badge = $("workspaceAccessModeBadge");
  const text = $("workspaceAccessModeText");
  const unlock = $("workspaceUnlockBtn");
  if (!badge || !text) return;
  badge.className = "access-mode-badge";
  if (unlock) unlock.hidden = true;
  if (workspaceComplimentaryState?.allowed) {
    badge.classList.add("complimentary");
    badge.textContent = "Complimentary";
    text.textContent = `${workspaceComplimentaryState.pages_remaining} of ${workspaceComplimentaryState.page_limit} page credits remain. Generation reserves the selected maximum page target.`;
  } else if (workspaceAccessState?.temporary_open) {
    badge.classList.add("open");
    badge.textContent = "Open access";
    const expiry = workspaceAccessState.open_until ? new Date(workspaceAccessState.open_until).toLocaleString() : "the developer closes it";
    text.textContent = `Temporary open access is active until ${expiry}. Chapter payment is bypassed during this window.`;
  } else if (workspaceAccessState?.payment_required) {
    badge.classList.add("locked");
    badge.textContent = "Payment required";
    text.textContent = workspaceHasPaidCredential() ? "Paid chapter access is stored on this device." : "Free Starter is disabled. Use paid, authorised internal or complimentary access.";
  } else {
    badge.textContent = workspaceHasPaidCredential() ? "Paid" : "Commercial";
    text.textContent = workspaceHasPaidCredential() ? "Paid chapter access is stored on this device." : "Normal access is active. Eligible Chapter One users may use the Free Starter, otherwise unlock the chapter or use a complimentary token.";
  }
  if (unlock && currentProjectId && !workspaceComplimentaryState?.allowed && !workspaceAccessState?.temporary_open && !workspaceHasPaidCredential() && !(workspaceAccessState?.free_starter_enabled && workspaceFreeStarterEligible())) unlock.hidden = false;
  updateWorkspaceFlow();
}

async function refreshWorkspaceAccessStatus() {
  if (!window.ProjectReadyPayments) return;
  try { workspaceAccessState = await ProjectReadyPayments.accessStatus("thesis_workspace"); }
  catch (_) { workspaceAccessState = {mode:"commercial",free_starter_enabled:true}; }
  const stored = ProjectReadyPayments.getComplimentaryCredential?.();
  if ($("workspaceComplimentaryToken") && stored?.token && !$("workspaceComplimentaryToken").value) $("workspaceComplimentaryToken").value = stored.token;
  if ($("workspaceComplimentaryEmail") && stored?.email && !$("workspaceComplimentaryEmail").value) $("workspaceComplimentaryEmail").value = stored.email;
  if (stored?.token) {
    try { workspaceComplimentaryState = await ProjectReadyPayments.complimentaryStatus("thesis_workspace"); }
    catch (_) { workspaceComplimentaryState = null; }
  } else workspaceComplimentaryState = null;
  const status = $("workspaceComplimentaryStatus");
  if (status) {
    if (workspaceComplimentaryState?.allowed) status.textContent = `${workspaceComplimentaryState.label || "Complimentary access"}: ${workspaceComplimentaryState.pages_remaining} page credit(s) remaining, expires ${new Date(workspaceComplimentaryState.expires_at).toLocaleDateString()}. Your selected maximum page target must fit within the remaining balance.`;
    else if (stored?.token) status.textContent = workspaceComplimentaryState?.detail || "This saved complimentary token is not valid for Thesis Workspace.";
    else status.textContent = "";
  }
  renderWorkspaceAccessStatus();
}

async function applyWorkspaceComplimentaryAccess() {
  const token = $("workspaceComplimentaryToken")?.value.trim() || "";
  const email = $("workspaceComplimentaryEmail")?.value.trim() || "";
  if (!token) {
    if ($("workspaceComplimentaryStatus")) $("workspaceComplimentaryStatus").textContent = "Enter the complimentary token first.";
    return;
  }
  ProjectReadyPayments.saveComplimentaryCredential(token, email);
  await refreshWorkspaceAccessStatus();
  if (!workspaceComplimentaryState?.allowed && $("workspaceComplimentaryDetails")) $("workspaceComplimentaryDetails").open = true;
}

async function clearWorkspaceComplimentaryAccess() {
  ProjectReadyPayments.clearComplimentaryCredential();
  workspaceComplimentaryState = null;
  if ($("workspaceComplimentaryToken")) $("workspaceComplimentaryToken").value = "";
  if ($("workspaceComplimentaryEmail")) $("workspaceComplimentaryEmail").value = "";
  if ($("workspaceComplimentaryStatus")) $("workspaceComplimentaryStatus").textContent = "Complimentary token cleared from this device.";
  await refreshWorkspaceAccessStatus();
}

function ensureWorkspaceClearButton() {
  let button = $("clearWorkspaceBtn");
  if (button) {
    button.hidden = false;
    button.style.removeProperty("display");
    return button;
  }

  const createButton = $("createProjectBtn");
  if (!createButton) return null;

  let actionRow = createButton.closest(".project-start-actions, .actions");
  if (!actionRow) {
    actionRow = document.createElement("div");
    actionRow.className = "actions project-start-actions";
    createButton.parentNode?.insertBefore(actionRow, createButton);
    actionRow.appendChild(createButton);
  }

  button = document.createElement("button");
  button.id = "clearWorkspaceBtn";
  button.type = "button";
  button.className = "secondary-action workspace-clear-action";
  button.textContent = "Clear and start new job";
  button.setAttribute("aria-label", "Clear all current thesis workspace entries and start a new job");
  createButton.insertAdjacentElement("afterend", button);
  return button;
}

function clearWorkspaceStoredJobState() {
  currentProjectId = null;
  activeBackgroundJob = null;
  for (const storage of [sessionStorage, localStorage]) {
    try { storage.removeItem(CURRENT_PROJECT_STORAGE_KEY); } catch (_) {}
    try {
      Object.keys(storage)
        .filter((key) => key.startsWith("projectready-background-job:"))
        .forEach((key) => storage.removeItem(key));
    } catch (_) {}
  }
}

function resetWorkspaceBrowserFields() {
  document.querySelectorAll("input, textarea, select").forEach((field) => {
    if (field.tagName === "SELECT") {
      const defaultIndex = Array.from(field.options || []).findIndex((option) => option.defaultSelected);
      field.selectedIndex = defaultIndex >= 0 ? defaultIndex : 0;
      return;
    }
    if (field.type === "checkbox" || field.type === "radio") {
      field.checked = field.defaultChecked;
      return;
    }
    if (field.type === "file") {
      field.value = "";
      return;
    }
    field.value = field.defaultValue || "";
  });

  currentProjectId = null;
  currentChapter = 1;
  currentSections = [];
  latestSourceSearchResult = null;
  accumulatedSourceBank = [];
  selectedPapers = [];
  uploadedRevisionText = "";
  uploadedRevisionFilename = "";
  alignmentUploadAttached = false;
  savedProjectDrafts = {};
  draftRequestInFlight = false;
  customPageTargets = {};
  activeBackgroundJob = null;
  setBackgroundJobPanel(null);

  if ($("draftOutput")) $("draftOutput").value = "";
  if ($("draftPreview")) $("draftPreview").textContent = "";
  if ($("scoreBox")) $("scoreBox").textContent = "";
  if ($("checkTable")) $("checkTable").querySelector("tbody").innerHTML = "";
  if ($("sourceResults")) $("sourceResults").innerHTML = "";
  if ($("selectedPapersList")) $("selectedPapersList").innerHTML = "";
  if ($("selectedPapersStatus")) $("selectedPapersStatus").textContent = "";
  if ($("workspaceRecoveryResults")) $("workspaceRecoveryResults").innerHTML = "";
  if ($("previousChapterStatus")) $("previousChapterStatus").textContent = "";
  if ($("revisionStatus")) $("revisionStatus").textContent = "";
  if ($("resultsStatus")) $("resultsStatus").textContent = "";
  if ($("sourceStatus")) $("sourceStatus").textContent = "";
  if ($("draftStatus")) $("draftStatus").textContent = "";
  if ($("downloadDraftBtn")) $("downloadDraftBtn").disabled = true;
  if ($("downloadCheckBtn")) $("downloadCheckBtn").disabled = true;
  if ($("downloadProjectBtn")) $("downloadProjectBtn").disabled = true;
  if ($("saveRecoveryBtn")) $("saveRecoveryBtn").disabled = true;
  if ($("saveProjectProfileBtn")) $("saveProjectProfileBtn").disabled = true;
  if ($("researchCockpit")) $("researchCockpit").hidden = true;
  currentResearchCockpit = null;
  if ($("projectStatus")) $("projectStatus").textContent = "Old project entries were cleared. Complete the new project profile to begin.";

  if ($("chapterSelect")) {
    $("chapterSelect").selectedIndex = 0;
    currentChapter = Number($("chapterSelect").value || 1);
  }
  if (template && $("chapterSelect")) renderSections();
  syncPageTargetControlsForChapter();
  updateLevelHint();
  updateChapterSpecificUi();
}

async function clearWorkspaceAndStartNewJob() {
  if (activeBackgroundJob && ["queued", "retrying"].includes(activeBackgroundJob.job?.status)) {
    try { await cancelActiveBackgroundJob(); } catch (_) {}
  }
  clearWorkspaceStoredJobState();
  const clean = new URL("/workspace", window.location.origin);
  clean.searchParams.set(WORKSPACE_NEW_JOB_PARAM, "1");
  clean.searchParams.set("_", String(Date.now()));
  window.location.replace(clean.pathname + clean.search);
}

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
  const custom = customPageTargets[String(chapter)];
  const pages = custom ? `${custom.minimum}-${custom.maximum}` : chapterPageTargets[level]?.[chapter];
  if (!pages || chapter > 5) {
    hint.textContent = "Depth for this output is based on the selected scope and sections.";
  } else if (custom) {
    hint.textContent = `Custom target depth for Chapter ${chapter}: about ${pages} pages. Very long chapters will be developed through staged section batches where needed.`;
  } else {
    hint.textContent = `Target depth for Chapter ${chapter}: about ${pages} pages, with citations distributed across substantive paragraphs. Final pagination depends on tables, figures, equations and references.`;
  }
  hint.hidden = false;
}

function currentPageTargetInput() {
  const mode = $("pageTargetMode")?.value || "default";
  const min = Number($("customPageMin")?.value || 0);
  const max = Number($("customPageMax")?.value || 0);
  const chapter = Number(currentChapter || 1);
  if (mode !== "custom") return { mode: "default", chapter };
  if (!Number.isFinite(min) || !Number.isFinite(max) || min < 1 || max < min) {
    return { mode: "invalid", chapter, minimum: min, maximum: max };
  }
  return { mode: "custom", chapter, minimum: Math.round(min), maximum: Math.round(max) };
}

function updateCustomPageTargetFromInputs() {
  const mode = $("pageTargetMode")?.value || "default";
  const minInput = $("customPageMin");
  const maxInput = $("customPageMax");
  const status = $("pageTargetStatus");
  const chapter = Number(currentChapter || 1);
  const customEnabled = mode === "custom";
  if (minInput) minInput.disabled = !customEnabled;
  if (maxInput) maxInput.disabled = !customEnabled;
  if (!customEnabled) {
    delete customPageTargets[String(chapter)];
    if (status) status.textContent = "Default target will be used unless you set a custom range.";
    updateLevelHint();
    return;
  }
  const target = currentPageTargetInput();
  if (target.mode === "custom") {
    customPageTargets[String(chapter)] = { minimum: target.minimum, maximum: target.maximum };
    if (status) status.textContent = `Custom target saved for Chapter ${chapter}: ${target.minimum}-${target.maximum} pages.`;
  } else if (status) {
    status.textContent = "Enter a valid custom range. The maximum page value must be greater than or equal to the minimum.";
  }
  updateLevelHint();
}

function syncPageTargetControlsForChapter() {
  const chapter = Number(currentChapter || 1);
  const custom = customPageTargets[String(chapter)];
  if ($("pageTargetMode")) $("pageTargetMode").value = custom ? "custom" : "default";
  if ($("customPageMin")) $("customPageMin").value = custom?.minimum || "";
  if ($("customPageMax")) $("customPageMax").value = custom?.maximum || "";
  updateCustomPageTargetFromInputs();
}

function collectCustomPageTargetsForProfile() {
  const target = currentPageTargetInput();
  if (target.mode === "custom") {
    customPageTargets[String(target.chapter)] = { minimum: target.minimum, maximum: target.maximum };
  }
  return { ...customPageTargets };
}

async function api(path, options = {}) {
  const actionRoute = /\/(draft|check|draft-jobs)$/.test(path);
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
  await refreshWorkspaceAccessStatus().catch(() => {});
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
  button.hidden = false;

  if (!currentProjectId) {
    status.textContent = "Create the project profile to activate chapter access.";
    return;
  }

  if (workspaceComplimentaryState?.allowed) {
    panel.classList.add("is-active");
    status.textContent = `Complimentary access is active. ${workspaceComplimentaryState.pages_remaining} page credit(s) remain. The selected maximum page target must fit within this balance.`;
    button.hidden = true;
    return;
  }
  if (workspaceAccessState?.temporary_open) {
    panel.classList.add("is-active");
    status.textContent = "Temporary Open Access is active. No chapter payment is required during the developer-defined access window.";
    button.hidden = true;
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
  if (workspaceAccessState?.payment_required) {
    panel.classList.add("is-warning");
    status.textContent = "Payment Required mode is active. Free Starter is disabled. Use paid, authorised internal or complimentary access.";
  } else if (freeEligible) {
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
    if ($("format_notes")) $("format_notes").value = profile.format_notes || "";
    if ($("expectedChapters")) $("expectedChapters").value = profile.expected_chapters || 5;
    if ($("backgroundStructure")) $("backgroundStructure").value = profile.background_structure || "continuous_narrative";
    if ($("purposeStatementStyle")) $("purposeStatementStyle").value = profile.purpose_statement_style || "concise_general_objective";
    if ($("automaticSourceSupport")) $("automaticSourceSupport").checked = profile.automatic_source_support !== false;
    if ($("research_area")) $("research_area").value = profile.research_area || "";
    if ($("citationDisciplineMatrix")) $("citationDisciplineMatrix").value = profile.citation_discipline_matrix || "auto";
    if ($("study_context")) $("study_context").value = profile.study_context || "";
    if ($("citation_evidence_notes")) $("citation_evidence_notes").value = profile.citation_evidence_notes || "";
    if ($("research_approach") && profile.research_approach) $("research_approach").value = profile.research_approach;
    if ($("data_type") && profile.data_type) $("data_type").value = profile.data_type;
    if ($("objectives")) $("objectives").value = (profile.objectives || []).join("\n");
    if ($("research_questions")) $("research_questions").value = (profile.research_questions || []).join("\n");
    if ($("hypotheses")) $("hypotheses").value = (profile.hypotheses || []).join("\n");
    const restoredVariables = profile.variables?.raw_variables || profile.variables?.constructs || [];
    if ($("variables_constructs")) $("variables_constructs").value = Array.isArray(restoredVariables) ? restoredVariables.join("\n") : String(restoredVariables || "");
    accumulatedSourceBank = Array.isArray(profile.source_bank) ? profile.source_bank : [];
    selectedPapers = Array.isArray(profile.selected_papers) ? profile.selected_papers : [];
    renderSelectedPapers();
    latestSourceSearchResult = profile.retrieved_sources && typeof profile.retrieved_sources === "object" ? profile.retrieved_sources : null;
    const contribution = profile.student_contribution || {};
    if ($("draftMaturity")) $("draftMaturity").value = contribution.draft_maturity || profile.draft_maturity || $("draftMaturity").value;
    if ($("centralArgument")) $("centralArgument").value = contribution.central_argument || "";
    if ($("localContextNotes")) $("localContextNotes").value = contribution.local_context_notes || "";
    if ($("evidenceAnchors")) $("evidenceAnchors").value = contribution.evidence_anchors || "";
    if ($("supervisorComments")) $("supervisorComments").value = contribution.supervisor_comments || "";
    if ($("preferredStyle")) $("preferredStyle").value = contribution.preferred_style || contribution.phrases_to_avoid || "";
    if ($("writingSample")) $("writingSample").value = contribution.writing_sample || "";
    if ($("humanRevisionPass")) $("humanRevisionPass").checked = contribution.human_revision_pass !== false;
    if ($("humanizerMode")) $("humanizerMode").value = contribution.humanizer_mode || profile.humanizer_mode || "balanced";
    if ($("academicIntegrityDeclaration")) $("academicIntegrityDeclaration").checked = Boolean(profile.academic_integrity_confirmed);
    if ($("userContributionDeclaration")) $("userContributionDeclaration").checked = Boolean(profile.user_contribution_confirmed);
    customPageTargets = profile.custom_page_targets || {};
    syncPageTargetControlsForChapter();
    const alignmentUploads = profile.uploaded_alignment_chapters || {};
    const alignmentCount = Array.isArray(alignmentUploads) ? alignmentUploads.length : Object.keys(alignmentUploads || {}).length;
    savedProjectDrafts = project.drafts || {};
    if ($("draftOutput")) $("draftOutput").value = savedProjectDrafts[String(currentChapter)] || "";
    currentClaimSupportReview = (profile.claim_support_reviews || {})[`draft:${Number(currentChapter)}`] || null;
    renderClaimSupportReview(currentClaimSupportReview);
    renderDraftPreview($("draftOutput")?.value || "");
    alignmentUploadAttached = alignmentCount > 0;
    if ($("previousChapterStatus") && alignmentCount) {
      $("previousChapterStatus").textContent = `${alignmentCount} previous-chapter/full-work alignment upload(s) are already attached to this project.`;
    }
    if ($("saveRecoveryBtn")) $("saveRecoveryBtn").disabled = false;
    if ($("saveProjectProfileBtn")) $("saveProjectProfileBtn").disabled = false;
    if ($("downloadProjectBtn")) $("downloadProjectBtn").disabled = Object.keys(savedProjectDrafts || {}).length === 0;
    if ($("projectStatus")) $("projectStatus").textContent = project.recovery_enabled
      ? `Project restored: ${project.id}. Recovery is enabled.`
      : `Project restored: ${project.id}. Add a recovery email and PIN to make the ID recoverable.`;
    await refreshResearchCockpit();
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
  const previousBox = $("previousChaptersBox");
  if (previousBox) previousBox.hidden = Number(currentChapter || 1) <= 1;
  const previousSelect = $("previousChapterNumber");
  if (previousSelect && Number(currentChapter || 1) > 1) {
    const selected = Number(previousSelect.value || 1);
    if (selected !== 0 && selected >= Number(currentChapter || 1)) {
      previousSelect.value = String(Math.max(1, Number(currentChapter || 2) - 1));
    }
  }
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
    syncPageTargetControlsForChapter();
    updateLevelHint();
    if ($("draftOutput")) $("draftOutput").value = savedProjectDrafts[String(currentChapter)] || "";
    currentClaimSupportReview = null;
    renderDraftPreview($("draftOutput")?.value || "");
    if (currentProjectId && $("draftOutput")?.value.trim()) refreshClaimSupportReview().catch(() => {});
    updatePaymentPanel();
    refreshVersionHistory();
  });
  renderSections();
  syncPageTargetControlsForChapter();
  updateLevelHint();
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
    const prompts = section.guiding_questions || [];
    const first = prompts[0] ? `
      <label>${prompts[0]}
        <textarea data-section="${section.section_id}" data-question="q1" rows="2"></textarea>
      </label>` : "";
    const additional = prompts.slice(1).map((q, idx) => `
      <label>${q}
        <textarea data-section="${section.section_id}" data-question="q${idx + 2}" rows="2"></textarea>
      </label>`).join("");
    const optional = additional ? `
      <details class="optional-fields prompt-options">
        <summary><span>Show more guidance fields</span><small class="optional-summary-state"></small></summary>
        <div class="optional-fields-body">${additional}</div>
      </details>` : "";
    div.innerHTML = `<h3>${section.section_title}</h3>${first}${optional}`;
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
    custom_page_targets: collectCustomPageTargetsForProfile(),
    current_custom_page_target: currentPageTargetInput(),
    programme: "",
    department: "",
    institution: "",
    level: selectedLevel,
    academic_level_guidance: levelDepthGuidance[selectedLevel] || "",
    reference_currency_rule: "Aim for at least 70% of substantive references from the last five years. Where current references do not exist for a specific issue, use the most relevant credible available sources, including foundational theories, classic models, and essential older studies.",
    thesis_format: $("thesis_format") ? $("thesis_format").value : "Standard five-chapter thesis/dissertation",
    format_notes: $("format_notes") ? $("format_notes").value.trim() : "",
    background_structure: $("backgroundStructure") ? $("backgroundStructure").value : "continuous_narrative",
    purpose_statement_style: $("purposeStatementStyle") ? $("purposeStatementStyle").value : "concise_general_objective",
    automatic_source_support: $("automaticSourceSupport") ? $("automaticSourceSupport").checked : true,
    citation_discipline_matrix: $("citationDisciplineMatrix") ? $("citationDisciplineMatrix").value : "auto",
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
      human_revision_pass: $("humanRevisionPass") ? $("humanRevisionPass").checked : true,
      humanizer_mode: $("humanizerMode") ? $("humanizerMode").value : "balanced"
    },
    humanizer_mode: $("humanizerMode") ? $("humanizerMode").value : "balanced",
    research_approach: $("research_approach").value,
    data_type: $("data_type") ? $("data_type").value : "Primary data",
    variables: {
      raw_variables: lines($("variables_constructs") ? $("variables_constructs").value : "")
    },
    expected_chapters: $("expectedChapters") ? Math.max(3, Math.min(9, Number($("expectedChapters").value || 5))) : 5,
    other_chapter_title: $("otherChapterTitle") ? $("otherChapterTitle").value.trim() : "",
    other_chapter_instructions: $("otherChapterInstructions") ? $("otherChapterInstructions").value.trim() : "",
    objectives: lines($("objectives").value),
    research_questions: lines($("research_questions") ? $("research_questions").value : ""),
    hypotheses: lines($("hypotheses") ? $("hypotheses").value : ""),
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
  if (!area && context.length < 30) warnings.push("research area and study context are limited");
  if (!objectives.length && answerText.length < 60) warnings.push("objectives, research questions or guided-section answers are limited");
  if (contributionText.length < 140) warnings.push("evidence, argument, context or supervisor direction is limited");
  if (Number(currentChapter || 1) >= 2) {
    const pastedAlignment = $('previousChaptersContext')?.value.trim() || "";
    if (!alignmentUploadAttached && !hasSavedEarlierDraftForAlignment() && pastedAlignment.length < 80) {
      warnings.push("earlier chapter alignment context has not been supplied, so the draft will include alignment-confirmation placeholders");
    }
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
  if ($("saveProjectProfileBtn")) $("saveProjectProfileBtn").disabled = false;
  $("projectStatus").textContent = result.recovery_enabled
    ? `Project created: ${result.id}. Recovery is enabled for the saved email and PIN.`
    : `Project created: ${result.id}. Add a recovery email and PIN to protect access if the ID is lost.`;
  ensureWorkspaceClearButton();
  updateChapterSpecificUi();
  await refreshResearchCockpit();
  await updatePaymentPanel();
  updateWorkspaceFlow();
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
  const matrix = metrics?.citation_matrix || {};
  const discipline = matrix.discipline_label || "Auto-detected discipline";
  const target = metrics?.citation_target || {};
  const verifiedDensity = Number(metrics?.verified_references_per_1000_words ?? metrics?.citation_occurrences_per_1000_words ?? 0);
  const targetText = target.minimum !== undefined
    ? `${target.minimum}-${target.maximum} verified referenced works per 1,000 words`
    : "the discipline-and-section matrix";
  const integrity = metrics?.citation_integrity || {};
  const integrityText = integrity.unverified_source_count
    ? ` ${integrity.unverified_source_count} unverified generated citation(s) were blocked.`
    : " Citation integrity gate passed.";
  const metricText = metrics
    ? ` Estimated ${metrics.estimated_pages} pages from ${Number(metrics.word_count || 0).toLocaleString()} words. Verified citation density: ${verifiedDensity} per 1,000 words, target ${targetText} for ${discipline}.${integrityText}`
    : "";
  if (metrics && !metrics.depth_target_reached) {
    status.textContent = `Working draft developed but remains below the planned depth target.${metricText} Add more verified evidence, results or source material, then revise or regenerate.`;
  } else if (metrics?.citation_density_status === "under_target") {
    status.textContent = `Working draft developed.${metricText} Citation density remains below the matrix range because ProjectReady will not fabricate or pad sources. Add or find more verified evidence if the section genuinely needs it.`;
  } else if (count > 8) {
    status.textContent = `Working draft developed.${metricText} Review generic transitions and add more project-specific evidence before any submission.`;
  } else {
    status.textContent = `Working draft developed from the information you supplied.${metricText} Review every source, fact and argument, then revise before any submission.`;
  }
}

function backgroundJobStorageKey(projectId = currentProjectId, chapter = currentChapter) {
  return `projectready-background-job:${projectId || "unknown"}:chapter-${chapter || 0}`;
}

function setBackgroundJobPanel(job = null) {
  const panel = $("backgroundJobPanel");
  if (!panel) return;
  panel.hidden = !job;
  if (!job) return;
  const progress = Math.max(0, Math.min(Number(job.progress || 0), 100));
  if ($("backgroundJobProgress")) $("backgroundJobProgress").value = progress;
  if ($("backgroundJobPercent")) $("backgroundJobPercent").textContent = `${progress}%`;
  if ($("backgroundJobStage")) $("backgroundJobStage").textContent = String(job.stage || job.status || "Queued").replaceAll("_", " ");
  if ($("backgroundJobMessage")) $("backgroundJobMessage").textContent = job.message || "Your request is being processed in the background.";
  if ($("cancelBackgroundJobBtn")) $("cancelBackgroundJobBtn").hidden = !["queued", "retrying"].includes(job.status);
}

function rememberBackgroundJob(data) {
  activeBackgroundJob = data;
  if (data?.job?.id && data?.job_token) {
    localStorage.setItem(backgroundJobStorageKey(data.job.project_id, data.job.chapter_number), JSON.stringify(data));
  }
}

function forgetBackgroundJob(job = activeBackgroundJob) {
  if (job?.job?.project_id) localStorage.removeItem(backgroundJobStorageKey(job.job.project_id, job.job.chapter_number));
  activeBackgroundJob = null;
  setBackgroundJobPanel(null);
}

async function readBackgroundJob(data) {
  const response = await fetch(`/api/jobs/${data.job.id}`, {
    headers: {"X-ProjectReady-Job-Token": data.job_token},
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The background request could not be checked.");
  return body.job;
}

async function pollBackgroundJob(data) {
  rememberBackgroundJob(data);
  let delay = 1500;
  while (true) {
    const job = await readBackgroundJob(data);
    data.job = job;
    rememberBackgroundJob(data);
    setBackgroundJobPanel(job);
    if ($("draftStatus")) $("draftStatus").textContent = job.message || `Background request: ${job.status}.`;
    if (job.status === "completed") {
      forgetBackgroundJob(data);
      return job.result || {};
    }
    if (job.status === "failed") {
      forgetBackgroundJob(data);
      throw new Error(job.error || "The background request could not be completed. Your paid entitlement was returned where applicable.");
    }
    if (job.status === "cancelled") {
      forgetBackgroundJob(data);
      throw new Error("The queued request was cancelled.");
    }
    await new Promise(resolve => window.setTimeout(resolve, delay));
    delay = Math.min(5000, Math.round(delay * 1.25));
  }
}

function applyDraftResult(result) {
  hideAccessRequiredNotice();
  $("draftOutput").value = result.draft || "";
  savedProjectDrafts[String(currentChapter)] = result.draft || "";
  currentClaimSupportReview = result.claim_support_review || result.generation_metrics?.claim_support_review || null;
  renderClaimSupportReview(currentClaimSupportReview);
  renderDraftPreview(result.draft || "");
  showDraftQualityHint(result.draft || "", result.generation_metrics || null);
  if (result.warning) {
    $("draftStatus").textContent = result.warning + " Review the working draft and complete every placeholder before export.";
  }
  setClaimReviewExportGate();
  renderChapterContinuation(result.next_chapter || null);
  refreshResearchCockpit();
}



function claimReviewItems(review = currentClaimSupportReview) {
  if (!review) return [];
  return [...(review.claims || []), ...(review.paragraph_density_gaps || [])];
}

function findClaimReviewItem(itemId) {
  return claimReviewItems().find(item => String(item.id || "") === String(itemId || ""));
}

function setClaimReviewExportGate() {
  const ready = !currentClaimSupportReview || Boolean(currentClaimSupportReview.final_output_ready);
  if ($("downloadDraftBtn")) {
    $("downloadDraftBtn").disabled = !ready || !$('draftOutput')?.value.trim();
    $("downloadDraftBtn").classList.toggle('claim-review-locked', !ready);
    $("downloadDraftBtn").title = ready ? "" : "Complete the Claim Support Review before exporting the chapter.";
  }
  if ($("downloadProjectBtn")) {
    $("downloadProjectBtn").disabled = !ready || Object.keys(savedProjectDrafts || {}).length === 0;
    $("downloadProjectBtn").classList.toggle('claim-review-locked', !ready);
  }
}

function candidateAuthorText(candidate) {
  const authors = Array.isArray(candidate?.authors) ? candidate.authors : [candidate?.authors].filter(Boolean);
  return authors.slice(0, 4).join(', ') || 'Author metadata unavailable';
}

function renderClaimSupportCandidates(item) {
  const raw = Array.isArray(item.candidates) ? item.candidates : [];
  const seen = new Set();
  const candidates = raw.filter(candidate => {
    const key = String(candidate?.candidate_id || candidate?.doi || candidate?.title || '').toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (!candidates.length) return '';
  const approvedIds = new Set((item.approved_sources || []).map(source => source.candidate_id || source.doi || source.title));
  return `<div class="claim-support-candidates">${candidates.map(candidate => {
    const id = escapeHtml(candidate.candidate_id || '');
    const identity = candidate.candidate_id || candidate.doi || candidate.title;
    const approved = approvedIds.has(identity);
    const locator = candidate.doi ? `https://doi.org/${String(candidate.doi).replace('https://doi.org/','').replace('http://doi.org/','')}` : candidate.url;
    const link = locator ? `<a href="${escapeHtml(locator)}" target="_blank" rel="noopener">Open source</a>` : '';
    const evidence = candidate.evidence_excerpt ? `<p class="claim-source-evidence"><strong>Accessible evidence:</strong> ${escapeHtml(candidate.evidence_excerpt)}</p>` : `<p class="claim-source-evidence"><strong>Evidence text unavailable in the search record.</strong> Open the source and confirm it manually before approval.</p>`;
    const dbs = Array.isArray(candidate.databases_found) && candidate.databases_found.length ? candidate.databases_found.join(', ') : (candidate.database || 'scholarly index');
    const verification = candidate.verification_basis ? `<p class="claim-source-meta"><strong>Verified through:</strong> ${escapeHtml(dbs)}. ${escapeHtml(candidate.verification_basis)}</p>` : '';
    const manual = candidate.requires_manual_source_text_confirmation && candidate.citation_eligible ? `<label class="inline claim-support-small"><input type="checkbox" data-claim-source-reviewed="${id}"> I opened the source text and confirmed it supports this claim.</label>` : '';
    const approving = Boolean(candidate._approving);
    const button = !candidate.citation_eligible
      ? `<button type="button" class="secondary-action" disabled title="Incomplete bibliographic metadata">Not citation eligible</button>`
      : `<button type="button" class="secondary-action" data-approve-claim-source="${escapeHtml(item.id)}" data-candidate-id="${id}" ${approved || approving ? 'disabled' : ''}>${approved ? '✓ Approved' : approving ? 'Approving…' : 'Approve as support'}</button>`;
    return `<article class="claim-source-candidate ${approved ? 'claim-source-approved' : ''}" data-candidate-id="${id}">
      <strong>${escapeHtml(candidate.title || 'Untitled source')}</strong>
      <p class="claim-source-meta">${escapeHtml(candidateAuthorText(candidate))} (${escapeHtml(candidate.year || 'n.d.')}) · ${escapeHtml(candidate.journal || candidate.database || '')} ${link}</p>
      ${verification}${evidence}${manual}${button}
    </article>`;
  }).join('')}</div>`;
}

function claimSupportExternalLinks(item) {
  const searches = Array.isArray(item.external_searches) ? item.external_searches : [];
  if (!searches.length) return '';
  return `<div class="claim-support-external">${searches.map(search => `<a href="${escapeHtml(search.url || '#')}" target="_blank" rel="noopener">Also search ${escapeHtml(search.provider || 'external database')}</a>`).join(' · ')}</div>`;
}

function renderClaimSupportReview(review = currentClaimSupportReview) {
  currentClaimSupportReview = review || null;
  const panel = $("claimSupportReviewPanel");
  const list = $("claimSupportReviewList");
  const summary = $("claimSupportSummary");
  const badge = $("claimSupportReviewBadge");
  if (!panel || !list || !summary || !badge) return;
  if (!review) {
    panel.hidden = true;
    setClaimReviewExportGate();
    return;
  }
  panel.hidden = false;
  const ready = Boolean(review.final_output_ready);
  badge.textContent = ready ? 'Evidence gate passed' : 'Review required';
  badge.classList.toggle('ready', ready);
  const finalSummary = review.final_approval_summary || review.application_summary || null;
  const finalBlock = finalSummary ? `<div class="claim-final-approval"><strong>Final approval</strong><br>${Number(finalSummary.verified_citation_references_added || 0)} verified citation reference(s) added · ${Number(finalSummary.unique_verified_sources_added || 0)} unique source(s) · ${Number(finalSummary.ignored_items ?? review.ignored_item_count ?? 0)} item(s) ignored</div>` : '';
  summary.innerHTML = `<div><strong>${Number(review.unsupported_claim_count || 0)}</strong><br>claims still needing citation support</div><div><strong>${Number(review.under_supported_paragraph_count || 0)}</strong><br>paragraphs still below 2 verified sources</div><div><strong>${Number(review.paragraph_citation_audit?.minimum_coverage_percent ?? 0)}%</strong><br>paragraph minimum coverage</div><div><strong>${Number(review.ignored_item_count || 0)}</strong><br>items ignored by user</div>${finalBlock}`;
  const items = claimReviewItems(review);
  if (!items.length) {
    list.innerHTML = `<div class="claim-support-card"><strong>Claim-support review passed.</strong><p>Only unresolved evidence gaps are listed here. No evidence-bearing citation gaps remain under the current audit rules.</p></div>`;
  } else {
    list.innerHTML = items.map(item => {
      const isClaim = item.type === 'claim';
      const text = isClaim ? item.claim_text : item.excerpt;
      const title = isClaim ? 'Claim needs source support' : `Paragraph needs ${item.minimum_verified_sources || 2}-${item.preferred_verified_sources || 3} distinct verified sources`;
      const approved = Array.isArray(item.approved_sources) ? item.approved_sources.length : 0;
      const searching = Boolean(item._searching);
      const searchedDatabases = Array.isArray(item.search_databases) && item.search_databases.length ? `<p class="claim-support-small">Searched: ${escapeHtml(item.search_databases.join(', '))}</p>` : '';
      return `<article class="claim-support-card" data-claim-support-item="${escapeHtml(item.id)}">
        <h4>${escapeHtml(title)}</h4>
        <p class="claim-support-small">${escapeHtml(item.heading || 'Chapter body')} · ${isClaim ? `paragraph ${item.paragraph_index}, sentence ${item.sentence_index}` : `paragraph ${item.paragraph_index}`} · ${approved} source(s) approved</p>
        <div class="claim-support-claim">${escapeHtml(text || '')}</div>
        <div class="actions compact-actions">
          <button type="button" class="secondary-action" data-find-claim-sources="${escapeHtml(item.id)}" ${searching ? 'disabled' : ''}>${searching ? 'Searching…' : 'Find verified sources'}</button>
          <button type="button" class="secondary-action claim-ignore-action" data-ignore-claim-support="${escapeHtml(item.id)}" ${searching ? 'disabled' : ''}>Ignore</button>
        </div>
        ${searching ? '<div class="claim-search-progress"><span class="claim-spinner" aria-hidden="true"></span> Searching OpenAlex, Crossref, Semantic Scholar, ERIC, DataCite, Europe PMC and PubMed…</div>' : ''}
        ${searchedDatabases}${claimSupportExternalLinks(item)}${renderClaimSupportCandidates(item)}
      </article>`;
    }).join('');
  }
  list.querySelectorAll('[data-find-claim-sources]').forEach(button => button.addEventListener('click', () => findSourcesForClaimReviewItem(button.dataset.findClaimSources).catch(err => { if ($('claimSupportStatus')) $('claimSupportStatus').textContent = err.message || 'Source search failed.'; })));
  list.querySelectorAll('[data-approve-claim-source]').forEach(button => button.addEventListener('click', () => approveClaimReviewSource(button.dataset.approveClaimSource, button.dataset.candidateId).catch(err => { if ($('claimSupportStatus')) $('claimSupportStatus').textContent = err.message || 'Source approval failed.'; })));
  list.querySelectorAll('[data-ignore-claim-support]').forEach(button => button.addEventListener('click', () => ignoreClaimReviewItem(button.dataset.ignoreClaimSupport).catch(err => { if ($('claimSupportStatus')) $('claimSupportStatus').textContent = err.message || 'Item could not be ignored.'; })));
  renderDraftPreview($("draftOutput")?.value || "");
  setClaimReviewExportGate();
}

async function findSourcesForClaimReviewItem(itemId) {
  if (!currentProjectId) throw new Error('Create or recover the project first.');
  const item = findClaimReviewItem(itemId);
  if (!item) throw new Error('This claim is no longer in the current review.');
  item._searching = true;
  renderClaimSupportReview(currentClaimSupportReview);
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = 'Searching OpenAlex, Crossref, Semantic Scholar, ERIC, DataCite, Europe PMC and PubMed. Google Scholar will also be offered for manual checking…';
  try {
    const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/claim-support/find-sources`, {
      method: 'POST', body: JSON.stringify({workflow:'draft', chapter_number:Number(currentChapter), claim_id:itemId, query:item.search_query || item.claim_text || item.excerpt || '', max_results:16})
    });
    item.candidates = data.candidates || [];
    item.search_databases = data.databases || [];
    item.external_searches = data.external_searches || [];
    item.provider_errors = data.provider_errors || [];
    if ($('claimSupportStatus')) {
      const failures = item.provider_errors.length ? ` ${item.provider_errors.length} database(s) were temporarily unavailable.` : '';
      $('claimSupportStatus').textContent = `${item.candidates.length} verified candidate source(s) found after searching ${item.search_databases.length} databases.${failures} Review evidence before approval.`;
    }
  } finally {
    item._searching = false;
    renderClaimSupportReview(currentClaimSupportReview);
  }
}

async function approveClaimReviewSource(itemId, candidateId) {
  const item = findClaimReviewItem(itemId);
  const candidate = (item?.candidates || []).find(source => String(source.candidate_id || '') === String(candidateId || ''));
  if (!item || !candidate) throw new Error('Source candidate is no longer available.');
  if (!candidate.citation_eligible) throw new Error('This result does not have complete verified bibliographic metadata and cannot be cited.');
  const reviewedBox = document.querySelector(`[data-claim-source-reviewed="${CSS.escape(String(candidateId))}"]`);
  const manualConfirmed = candidate.requires_manual_source_text_confirmation ? Boolean(reviewedBox?.checked) : false;
  if (candidate.requires_manual_source_text_confirmation && !manualConfirmed) throw new Error('Open the source and tick the confirmation that you checked its text before approving it.');
  candidate._approving = true;
  renderClaimSupportReview(currentClaimSupportReview);
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = 'Approving verified source and clearing the matching source-needed marker…';
  try {
    const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/claim-support/approve`, {
      method:'POST', body:JSON.stringify({workflow:'draft', chapter_number:Number(currentChapter), claim_id:itemId, candidate_id:candidateId, confirm_claim_support:true, confirm_source_text_reviewed:manualConfirmed})
    });
    item.approved_sources = [...(item.approved_sources || []), {...candidate, candidate_id:candidate.candidate_id}].slice(0,3);
    if (data.text && $("draftOutput")) {
      $("draftOutput").value = data.text;
      savedProjectDrafts[String(currentChapter)] = data.text;
    }
    if ($('claimSupportStatus')) $('claimSupportStatus').textContent = data.message || 'Source approved.';
  } finally {
    candidate._approving = false;
    renderClaimSupportReview(currentClaimSupportReview);
  }
}

async function ignoreClaimReviewItem(itemId) {
  if (!currentProjectId) throw new Error('Create or recover the project first.');
  const item = findClaimReviewItem(itemId);
  if (!item) throw new Error('This claim is no longer in the current review.');
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = 'Ignoring this item and removing its source-needed marker…';
  const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/claim-support/ignore`, {
    method:'POST', body:JSON.stringify({workflow:'draft', chapter_number:Number(currentChapter), claim_id:itemId})
  });
  if (data.text && $("draftOutput")) {
    $("draftOutput").value = data.text;
    savedProjectDrafts[String(currentChapter)] = data.text;
  }
  currentClaimSupportReview = data.review || currentClaimSupportReview;
  renderClaimSupportReview(currentClaimSupportReview);
  renderDraftPreview($("draftOutput")?.value || '');
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = data.message || 'Item ignored.';
}

async function applyApprovedClaimSources() {
  if (!currentProjectId) throw new Error('Create or recover the project first.');
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = 'Finalising only approved, verified citations and re-running citation density and claim-support checks…';
  const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/claim-support/apply-approved`, {
    method:'POST', body:JSON.stringify({workflow:'draft', chapter_number:Number(currentChapter), citation_style:'APA 7th'})
  });
  $("draftOutput").value = data.text || $("draftOutput").value;
  savedProjectDrafts[String(currentChapter)] = $("draftOutput").value;
  currentClaimSupportReview = data.review || null;
  renderClaimSupportReview(currentClaimSupportReview);
  renderDraftPreview($("draftOutput").value);
  const summary = currentClaimSupportReview?.final_approval_summary || {};
  const prefix = `Final approval: ${Number(summary.verified_citation_references_added || 0)} verified citation reference(s) added from ${Number(summary.unique_verified_sources_added || 0)} unique source(s); ${Number(summary.ignored_items || 0)} item(s) ignored.`;
  const remainder = currentClaimSupportReview?.final_output_ready
    ? ' Citation density and claim-support checks now pass. Export is unlocked.'
    : ` ${Number(summary.remaining_claims_without_citations || 0)} unsupported claim(s) and ${Number(summary.remaining_paragraph_density_gaps || 0)} paragraph density gap(s) remain.`;
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = prefix + remainder;
}

async function refreshClaimSupportReview() {
  if (!currentProjectId) return;
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = 'Re-running the verified citation-density and claim-support audit…';
  const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/claim-support-review?workflow=draft&chapter_number=${Number(currentChapter)}`);
  currentClaimSupportReview = data.review || null;
  renderClaimSupportReview(currentClaimSupportReview);
  if ($('claimSupportStatus')) $('claimSupportStatus').textContent = currentClaimSupportReview?.final_output_ready ? 'Audit passed. Only verified citations remain.' : 'Audit complete. Only unresolved citation-support items are listed below.';
}


function continuationLines(value) {
  return Array.isArray(value) ? value.join("\n") : String(value || "");
}

function renderProvisionalStatistics(items = []) {
  const panel = $("provisionalStatisticsPanel");
  const list = $("provisionalStatisticsList");
  if (!panel || !list) return;
  const usable = (items || []).filter(item => item && item.status !== "rejected");
  panel.hidden = usable.length === 0;
  list.innerHTML = usable.map(item => {
    const status = item.status === "confirmed" ? "Confirmed" : "Needs confirmation";
    const actions = item.status === "confirmed"
      ? `<button type="button" class="secondary-action" data-stat-decision="rejected" data-stat-id="${escapeHtml(item.id)}">Reject</button>`
      : `<button type="button" class="primary-action" data-stat-decision="confirmed" data-stat-id="${escapeHtml(item.id)}">Confirm source and context</button><button type="button" class="secondary-action" data-stat-decision="rejected" data-stat-id="${escapeHtml(item.id)}">Reject</button>`;
    const locator = item.source_locator ? `<a href="${escapeHtml(item.source_locator)}" target="_blank" rel="noopener">Open source</a>` : "";
    return `<article class="provisional-statistic-card ${item.status === "confirmed" ? "confirmed" : "pending"}">
      <div class="provisional-statistic-status">${escapeHtml(status)}</div>
      <p class="provisional-statistic-text">${escapeHtml(item.statement || "")}</p>
      <p class="provisional-statistic-source"><strong>Source:</strong> ${escapeHtml(item.source_label || item.source_title || "Verified source record")} ${locator}</p>
      <div class="actions compact-actions">${actions}</div>
    </article>`;
  }).join("");
  list.querySelectorAll("[data-stat-decision]").forEach(button => button.addEventListener("click", () => {
    decideProvisionalStatistic(button.dataset.statId, button.dataset.statDecision).catch(err => {
      if ($("continuationSaveStatus")) $("continuationSaveStatus").textContent = err.message || "The statistic decision could not be saved.";
    });
  }));
}

function renderChapterContinuation(linkage) {
  const panel = $("chapterContinuationPanel");
  if (!panel) return;
  currentContinuation = linkage && linkage.available ? linkage : null;
  panel.hidden = !currentContinuation;
  if (!currentContinuation) return;
  const from = Number(currentContinuation.completed_chapter || currentChapter || 1);
  const next = Number(currentContinuation.next_chapter || from + 1);
  if ($("continuationTitle")) $("continuationTitle").textContent = `Chapter ${from} is saved. Add Chapter ${next}?`;
  if ($("continuationMessage")) $("continuationMessage").textContent = currentContinuation.automatic_alignment || `ProjectReady will use Chapter ${from} automatically to align Chapter ${next}.`;
  const citation = currentContinuation.citation_target || {};
  const needs = currentContinuation.needs_confirmation || [];
  const carry = $("continuationCarryForward");
  if (carry) {
    carry.innerHTML = `<div><strong>Carried forward automatically</strong><span>Title, objectives, research questions, hypotheses, variables, terminology and Chapter ${from} context.</span></div>
      <div><strong>Next citation range</strong><span>${escapeHtml(citation.discipline_label || "Auto-detected discipline")}: ${escapeHtml(citation.minimum ?? "")}-${escapeHtml(citation.maximum ?? "")} verified referenced works per 1,000 words.</span></div>
      <div><strong>Needs your attention</strong><span>${needs.length ? escapeHtml(needs.map(item => item.label).join(", ")) : "No mandatory research-logic gap detected. You can still edit the carried-forward information."}</span></div>`;
  }
  if ($("continuationResearchTitle")) $("continuationResearchTitle").value = currentContinuation.title || "";
  if ($("continuationStudyContext")) $("continuationStudyContext").value = currentContinuation.study_context || "";
  if ($("continuationObjectives")) $("continuationObjectives").value = continuationLines(currentContinuation.objectives);
  if ($("continuationQuestions")) $("continuationQuestions").value = continuationLines(currentContinuation.research_questions);
  if ($("continuationHypotheses")) $("continuationHypotheses").value = continuationLines(currentContinuation.hypotheses);
  if ($("continuationVariables")) $("continuationVariables").value = continuationLines(currentContinuation.variables);
  if ($("continuationResearchApproach")) $("continuationResearchApproach").value = currentContinuation.research_approach || "";
  if ($("continuationNotes")) $("continuationNotes").value = "";
  if ($("continuationCorrectionDetails")) $("continuationCorrectionDetails").open = needs.length > 0;
  renderProvisionalStatistics(currentContinuation.provisional_statistics || []);
}

async function loadChapterContinuation(completedChapter = currentChapter) {
  if (!currentProjectId) return null;
  const result = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/continuation/${Number(completedChapter)}`);
  renderChapterContinuation(result.linkage || null);
  return result.linkage || null;
}

async function saveContinuationChanges() {
  if (!currentProjectId || !currentContinuation) throw new Error("No next-chapter transition is active.");
  const next = Number(currentContinuation.next_chapter || currentChapter + 1);
  const transitionNote = $("continuationNotes")?.value.trim() || "";
  const profilePatch = {
    title: $("continuationResearchTitle")?.value.trim() || currentContinuation.title || "",
    study_context: $("continuationStudyContext")?.value.trim() || "",
    objectives: lines($("continuationObjectives")?.value || ""),
    research_questions: lines($("continuationQuestions")?.value || ""),
    hypotheses: lines($("continuationHypotheses")?.value || ""),
    variables: {raw_variables: lines($("continuationVariables")?.value || "")},
    research_approach: $("continuationResearchApproach")?.value.trim() || "",
  };
  if (transitionNote) profilePatch.chapter_transition_notes = {[String(next)]: transitionNote};
  const result = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/profile`, {
    method: "PUT",
    body: JSON.stringify(profilePatch),
  });
  if ($("title")) $("title").value = profilePatch.title;
  if ($("study_context")) $("study_context").value = profilePatch.study_context;
  if ($("research_approach")) $("research_approach").value = profilePatch.research_approach;
  if ($("objectives")) $("objectives").value = profilePatch.objectives.join("\n");
  if ($("research_questions")) $("research_questions").value = profilePatch.research_questions.join("\n");
  if ($("hypotheses")) $("hypotheses").value = profilePatch.hypotheses.join("\n");
  if ($("variables_constructs")) $("variables_constructs").value = profilePatch.variables.raw_variables.join("\n");
  if ($("extraInstructions") && transitionNote) {
    $("extraInstructions").value = [$("extraInstructions").value.trim(), `Chapter ${next} transition information: ${transitionNote}`].filter(Boolean).join("\n\n");
  }
  if ($("continuationSaveStatus")) $("continuationSaveStatus").textContent = "Changes saved. They will guide the next chapter and later cross-chapter alignment.";
  await loadChapterContinuation(Number(currentContinuation.completed_chapter || currentChapter));
  return result;
}

async function decideProvisionalStatistic(statisticId, decision) {
  if (!currentProjectId) throw new Error("Create or restore the project first.");
  const result = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/provisional-statistics/${encodeURIComponent(statisticId)}/decision`, {
    method: "POST",
    body: JSON.stringify({decision}),
  });
  if ($("continuationSaveStatus")) $("continuationSaveStatus").textContent = result.message || "Statistic decision saved.";
  if (currentContinuation) {
    const refreshed = await loadChapterContinuation(Number(currentContinuation.completed_chapter || currentChapter));
    return refreshed;
  }
  return result;
}

async function continueToNextChapter() {
  if (!currentContinuation?.available) return;
  const completedChapter = Number(currentContinuation.completed_chapter || currentChapter);
  const next = Number(currentContinuation.next_chapter || currentChapter + 1);
  await saveContinuationChanges();
  if ($("chapterSelect")?.querySelector(`option[value="${next}"]`)) {
    $("chapterSelect").value = String(next);
    currentChapter = next;
    renderSections();
    syncPageTargetControlsForChapter();
    updateLevelHint();
    await updatePaymentPanel();
    await refreshWorkspaceAccessStatus();
    if ($("draftOutput")) $("draftOutput").value = savedProjectDrafts[String(next)] || "";
    renderDraftPreview($("draftOutput")?.value || "");
    if ($("chapterContinuationPanel")) $("chapterContinuationPanel").hidden = true;
    $("chapterSelectionStep")?.scrollIntoView({behavior: "smooth", block: "start"});
    if ($("draftStatus")) $("draftStatus").textContent = `Chapter ${completedChapter} remains linked automatically. Review the Chapter ${next} fields, add any new information needed, then develop the next chapter.`;
    updateWorkspaceFlow();
  }
}

async function resumeBackgroundDraftIfAvailable() {
  if (!currentProjectId) return;
  const keys = Object.keys(localStorage).filter(key => key.startsWith(`projectready-background-job:${currentProjectId}:`));
  if (!keys.length) return;
  try {
    const data = JSON.parse(localStorage.getItem(keys[0]) || "null");
    if (!data?.job?.id || !data?.job_token) return;
    currentChapter = Number(data.job.chapter_number || currentChapter);
    if ($("chapterSelect")?.querySelector(`option[value="${currentChapter}"]`)) {
      $("chapterSelect").value = String(currentChapter);
      renderSections();
    }
    draftRequestInFlight = true;
    if ($("draftBtn")) { $("draftBtn").disabled = true; $("draftBtn").textContent = "Background request running…"; }
    const result = await pollBackgroundJob(data);
    applyDraftResult(result);
    await updatePaymentPanel();
  } catch (error) {
    handleWorkspaceError(error, "draftStatus");
  } finally {
    draftRequestInFlight = false;
    if ($("draftBtn")) { $("draftBtn").disabled = false; $("draftBtn").textContent = "Develop Chapter Draft"; }
  }
}

async function cancelActiveBackgroundJob() {
  const data = activeBackgroundJob;
  if (!data?.job?.id || !data?.job_token) return;
  const response = await fetch(`/api/jobs/${data.job.id}/cancel`, {
    method: "POST",
    headers: {"X-ProjectReady-Job-Token": data.job_token},
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The queued request could not be cancelled.");
  forgetBackgroundJob(data);
  if ($("draftStatus")) $("draftStatus").textContent = body.job?.message || "The queued request was cancelled.";
}

async function generateDraft() {
  if (draftRequestInFlight) return;
  draftRequestInFlight = true;
  const draftButton = $("draftBtn");
  const originalButtonText = draftButton?.textContent || "Develop Chapter Draft";
  if (draftButton) {
    draftButton.disabled = true;
    draftButton.textContent = "Queueing request…";
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
        human_revision_pass: $("humanRevisionPass") ? $("humanRevisionPass").checked : true,
        humanizer_mode: $("humanizerMode") ? $("humanizerMode").value : "balanced"
      },
      human_revision_pass: $("humanRevisionPass") ? $("humanRevisionPass").checked : true,
      humanizer_mode: $("humanizerMode") ? $("humanizerMode").value : "balanced",
      academic_integrity_confirmed: $("academicIntegrityDeclaration") ? $("academicIntegrityDeclaration").checked : false,
      user_contribution_confirmed: $("userContributionDeclaration") ? $("userContributionDeclaration").checked : false,
      draft_consideration_warnings: considerationWarnings,
      allow_provisional_drafting: true,
      profile_updates: profileSnapshot,
      ...currentSourcePayload()
    };
    $("draftStatus").textContent = revisionMode
      ? "Queueing the chapter-strengthening request…"
      : "Queueing the working-draft request. You may leave this page after it enters the background queue.";
    const queued = await api(`/api/projects/${currentProjectId}/draft-jobs`, {method:"POST", body:JSON.stringify(payload)});
    rememberBackgroundJob(queued);
    setBackgroundJobPanel(queued.job);
    if (draftButton) draftButton.textContent = "Background request running…";
    const result = await pollBackgroundJob(queued);
    applyDraftResult(result);
    await updatePaymentPanel();
  } finally {
    draftRequestInFlight = false;
    if (draftButton) {
      draftButton.disabled = false;
      draftButton.textContent = originalButtonText;
    }
  }
}

function fillFieldFromSuggestion(fieldId, value, mode = "fill_empty") {
  const field = $(fieldId);
  const text = String(value || "").trim();
  if (!field || !text) return false;
  if (mode === "fill_empty" && String(field.value || "").trim()) return false;
  field.value = text;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

async function autofillFromChapterOneUpload() {
  const input = $("chapterOneAutofillFile");
  const status = $("chapterOneAutofillStatus");
  const preview = $("chapterOneAutofillPreview");
  if (!input || !input.files || input.files.length === 0) {
    if (status) status.textContent = "Please select an Introduction or Chapter One file first.";
    return;
  }
  const formData = new FormData();
  formData.append("file", input.files[0]);
  if (status) status.textContent = "Extracting Chapter One and preparing autofill suggestions...";
  const response = await fetch("/api/projects/extract-introduction-profile", {
    method: "POST",
    body: formData,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "The Introduction/Chapter One file could not be extracted.");
  const suggestions = data.profile_suggestions || {};
  const mode = $("chapterOneAutofillMode")?.value || "fill_empty";
  let filled = 0;
  if (fillFieldFromSuggestion("title", suggestions.title, mode)) filled += 1;
  if (fillFieldFromSuggestion("research_area", suggestions.research_area, mode)) filled += 1;
  if (fillFieldFromSuggestion("study_context", suggestions.study_context, mode)) filled += 1;
  if (fillFieldFromSuggestion("objectives", (suggestions.objectives || []).join("\n"), mode)) filled += 1;
  if (fillFieldFromSuggestion("variables_constructs", (suggestions.variables || []).join("\n"), mode)) filled += 1;
  const questionText = (suggestions.research_questions || []).join("\n");
  if (fillFieldFromSuggestion("research_questions", questionText, mode)) filled += 1;
  if (preview) preview.textContent = data.preview || "No preview available.";
  if (status) status.textContent = filled
    ? `Autofill completed. ${filled} field(s) were updated. Review all extracted content before creating or drafting the project.`
    : "Extraction completed, but no empty matching fields were updated. Choose Replace matching fields to overwrite existing values.";
}

async function uploadPreviousChapterForAlignment() {
  if (!currentProjectId) await createProject();
  const input = $("previousChapterFile");
  if (!input || !input.files || input.files.length === 0) {
    $("previousChapterStatus").textContent = "Please select an earlier chapter or complete-work file first.";
    return;
  }
  if (Number(currentChapter || 1) <= 1) {
    $("previousChapterStatus").textContent = "Previous-chapter alignment uploads are used from Chapter Two onward.";
    return;
  }

  const sourceNumber = Number($("previousChapterNumber")?.value || 1);
  if (sourceNumber !== 0 && sourceNumber >= Number(currentChapter || 1)) {
    $("previousChapterStatus").textContent = "Choose an earlier source chapter, or choose complete existing work / full thesis.";
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);
  formData.append("source_chapter_number", String(sourceNumber));
  formData.append("target_chapter_number", String(currentChapter || 2));

  $("previousChapterStatus").textContent = "Uploading and extracting previous-chapter context for alignment checks...";
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
  $("previousChapterStatus").textContent = result.message || `Uploaded ${result.filename} for Chapter ${result.target_chapter_number} alignment checks.`;
  $("previousChapterPreview").textContent = result.preview || "No preview available.";
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
  const errors = (result.provider_errors || []).length;
  const attached = result.attached_count_this_search ?? result.count ?? 0;
  const rejected = result.rejected_irrelevant_count || 0;
  const requested = result.requested_count || payload.max_results;
  $("sourceStatus").textContent = `Attached ${attached} relevant source(s) from a maximum of ${requested}. Rejected ${rejected} unrelated record(s). ${errors ? errors + " provider(s) could not be reached." : ""}`;
  await refreshResearchCockpit();
  updateWorkspaceFlow();
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


function selectedPaperAuthorsText(paper) {
  return Array.isArray(paper?.authors) ? paper.authors.join("; ") : String(paper?.authors || "");
}

function renderSelectedPapers() {
  const box = $("selectedPapersList");
  const status = $("selectedPapersStatus");
  if (!box) return;
  const papers = Array.isArray(selectedPapers) ? selectedPapers : [];
  const ready = papers.filter((paper) => paper?.citation_eligible).length;
  if (status && papers.length) {
    status.textContent = `${papers.length} of 50 selected papers attached. ${ready} citation-ready; ${papers.length - ready} need citation metadata confirmation.`;
  }
  if (!papers.length) {
    box.innerHTML = '<p class="hint">No selected papers have been uploaded. ProjectReady can still find literature automatically.</p>';
    return;
  }
  box.innerHTML = papers.map((paper, index) => {
    const ready = Boolean(paper.citation_eligible);
    const statusLabel = ready ? (paper.metadata_verified ? "Citation ready · verified" : "Citation ready · user confirmed") : "Metadata confirmation needed";
    const authors = selectedPaperAuthorsText(paper);
    const doi = paper.doi ? `<span><strong>DOI:</strong> ${escapeHtml(paper.doi)}</span>` : '';
    return `
      <article class="selected-paper-card" data-paper-id="${escapeHtml(paper.id || '')}">
        <div class="selected-paper-card-head">
          <div>
            <span class="selected-paper-number">Paper ${index + 1}</span>
            <strong>${escapeHtml(paper.title || paper.filename || 'Uploaded paper')}</strong>
            <small>${escapeHtml(paper.filename || '')}</small>
          </div>
          <span class="selected-paper-badge ${ready ? 'ready' : 'needs-confirmation'}">${escapeHtml(statusLabel)}</span>
        </div>
        <div class="selected-paper-meta">
          ${authors ? `<span>${escapeHtml(authors)}</span>` : '<span>Author details not confirmed</span>'}
          ${paper.year ? `<span>${escapeHtml(paper.year)}</span>` : '<span>Year not confirmed</span>'}
          ${doi}
        </div>
        <p class="hint">${escapeHtml(paper.provenance_note || '')}</p>
        <details class="selected-paper-metadata-editor">
          <summary>${ready ? 'Review citation details' : 'Confirm citation details before citing'}</summary>
          <div class="selected-paper-editor-grid">
            <label>Title<input data-paper-field="title" value="${escapeHtml(paper.title || '')}" /></label>
            <label>Authors, separate with semicolons<input data-paper-field="authors" value="${escapeHtml(authors)}" placeholder="First Author; Second Author" /></label>
            <label>Year<input data-paper-field="year" value="${escapeHtml(paper.year || '')}" inputmode="numeric" maxlength="5" /></label>
            <label>Journal / source<input data-paper-field="source" value="${escapeHtml(paper.source || '')}" /></label>
            <label>DOI<input data-paper-field="doi" value="${escapeHtml(paper.doi || '')}" placeholder="10.xxxx/xxxxx" /></label>
            <label>Stable URL<input data-paper-field="url" value="${escapeHtml(paper.url || '')}" /></label>
          </div>
          <div class="actions compact-actions">
            <button type="button" class="secondary-action" data-paper-save="${escapeHtml(paper.id || '')}">Save and confirm citation details</button>
            <button type="button" class="secondary-action danger-lite" data-paper-delete="${escapeHtml(paper.id || '')}">Remove paper</button>
          </div>
        </details>
      </article>`;
  }).join('');

  box.querySelectorAll('[data-paper-save]').forEach((button) => {
    button.addEventListener('click', () => saveSelectedPaperMetadata(button.dataset.paperSave).catch(err => handleWorkspaceError(err, 'selectedPapersStatus')));
  });
  box.querySelectorAll('[data-paper-delete]').forEach((button) => {
    button.addEventListener('click', () => removeSelectedPaper(button.dataset.paperDelete).catch(err => handleWorkspaceError(err, 'selectedPapersStatus')));
  });
}

async function uploadSelectedPapers() {
  if (!currentProjectId) await createProject();
  const input = $("selectedPaperFiles");
  const files = Array.from(input?.files || []);
  if (!files.length) {
    $("selectedPapersStatus").textContent = "Choose one or more papers first.";
    return;
  }
  if (selectedPapers.length + files.length > 50) {
    $("selectedPapersStatus").textContent = `A project can contain up to 50 selected papers. You currently have ${selectedPapers.length}.`;
    return;
  }
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  $("selectedPapersStatus").textContent = `Uploading and extracting ${files.length} selected paper(s)…`;
  const response = await fetch(`/api/projects/${currentProjectId}/selected-papers`, { method: 'POST', body: form });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Selected paper upload failed.');
  selectedPapers = Array.isArray(result.papers) ? result.papers : [];
  accumulatedSourceBank = Array.isArray(result.source_bank) ? result.source_bank : accumulatedSourceBank;
  if (input) input.value = '';
  renderSelectedPapers();
  const errors = Array.isArray(result.errors) ? result.errors.length : 0;
  $("selectedPapersStatus").textContent = `${result.uploaded_count || 0} paper(s) added. ${result.citation_ready || 0} citation-ready; ${result.needs_metadata_confirmation || 0} need citation metadata confirmation.${errors ? ` ${errors} file(s) could not be processed.` : ''}`;
  await refreshResearchCockpit();
  updateWorkspaceFlow();
}

async function saveSelectedPaperMetadata(paperId) {
  const card = document.querySelector(`.selected-paper-card[data-paper-id="${CSS.escape(String(paperId || ''))}"]`);
  if (!card) return;
  const value = (field) => card.querySelector(`[data-paper-field="${field}"]`)?.value.trim() || '';
  const payload = {
    title: value('title'),
    authors: value('authors'),
    year: value('year'),
    source: value('source'),
    doi: value('doi'),
    url: value('url'),
    confirm: true,
  };
  $("selectedPapersStatus").textContent = "Checking and saving citation details…";
  const result = await api(`/api/projects/${currentProjectId}/selected-papers/${encodeURIComponent(paperId)}`, { method: 'PATCH', body: JSON.stringify(payload) });
  selectedPapers = Array.isArray(result.papers) ? result.papers : selectedPapers;
  accumulatedSourceBank = Array.isArray(result.source_bank) ? result.source_bank : accumulatedSourceBank;
  renderSelectedPapers();
  $("selectedPapersStatus").textContent = result.paper?.citation_eligible
    ? "Citation details confirmed. ProjectReady may now cite this uploaded paper when the full-text evidence directly supports the claim."
    : "The paper remains evidence-only. Confirm a title, author(s) and publication year before ProjectReady can create a new citation from it.";
}

async function removeSelectedPaper(paperId) {
  const result = await api(`/api/projects/${currentProjectId}/selected-papers/${encodeURIComponent(paperId)}`, { method: 'DELETE' });
  selectedPapers = Array.isArray(result.papers) ? result.papers : [];
  accumulatedSourceBank = Array.isArray(result.source_bank) ? result.source_bank : accumulatedSourceBank;
  renderSelectedPapers();
  $("selectedPapersStatus").textContent = `${selectedPapers.length} selected paper(s) remain attached.`;
  await refreshResearchCockpit();
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
  await refreshResearchCockpit();
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


let currentResearchCockpit = null;

async function saveCurrentProjectProfile() {
  if (!currentProjectId) return createProject();
  const profile = collectProfile();
  if (!profile.title) throw new Error("Enter the project title before saving the research logic.");
  if (!responsibleUseConfirmed()) throw new Error("Confirm the academic-integrity and user-contribution declarations before saving.");
  delete profile.recovery_email;
  delete profile.recovery_pin;
  const result = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/profile`, {
    method: "PUT",
    body: JSON.stringify(profile),
  });
  if ($("projectStatus")) $("projectStatus").textContent = "Research logic saved. ProjectReady will use the updated objectives, questions, hypotheses, variables and study decisions across later chapters.";
  renderResearchCockpit(result.research_logic || null);
  return result;
}

function logicStatusLabel(value) {
  return value === "aligned" ? "Aligned" : value === "partial" ? "Partial" : "Needs action";
}

function renderResearchCockpit(data) {
  const panel = $("researchCockpit");
  if (!panel) return;
  if (!data) {
    panel.hidden = true;
    return;
  }
  currentResearchCockpit = data;
  panel.hidden = false;
  if ($("cockpitProjectTitle")) $("cockpitProjectTitle").textContent = data.project_title || "Research project progress";
  if ($("cockpitReadinessLabel")) $("cockpitReadinessLabel").textContent = data.readiness_label || "Project workflow readiness, not a grade";
  if ($("cockpitReadinessScore")) $("cockpitReadinessScore").textContent = `${Math.round(Number(data.readiness_score || 0))}%`;
  if ($("cockpitReadinessProgress")) $("cockpitReadinessProgress").value = Math.max(0, Math.min(100, Number(data.readiness_score || 0)));
  if ($("cockpitChapterProgress")) $("cockpitChapterProgress").textContent = `${Math.round(Number(data.chapter_progress || 0))}%`;
  if ($("cockpitAlignmentScore")) $("cockpitAlignmentScore").textContent = `${Math.round(Number(data.alignment_score || 0))}%`;
  if ($("cockpitSourceCount")) $("cockpitSourceCount").textContent = String(data.source_count || 0);
  if ($("cockpitComplianceScore")) $("cockpitComplianceScore").textContent = data.compliance_score === null || data.compliance_score === undefined ? "—" : `${Math.round(Number(data.compliance_score))}%`;

  const next = data.next_action || {};
  if ($("cockpitNextActionLabel")) $("cockpitNextActionLabel").textContent = next.label || "Continue my research";
  if ($("cockpitNextActionMessage")) $("cockpitNextActionMessage").textContent = next.message || "";
  if ($("cockpitNextActionBtn")) $("cockpitNextActionBtn").dataset.actionType = next.type || "chapter";
  if ($("cockpitNextActionBtn")) $("cockpitNextActionBtn").dataset.chapterNumber = String(next.chapter_number || 1);

  const track = $("cockpitChapterTrack");
  if (track) {
    track.innerHTML = (data.chapter_status || []).map(item => `
      <button type="button" class="cockpit-chapter-chip ${escapeHtml(item.status)}" data-cockpit-chapter="${Number(item.chapter_number)}">
        <strong>Chapter ${Number(item.chapter_number)}</strong>
        <span>${escapeHtml(item.status === "developed" ? "Developed" : item.status === "started" ? "Started" : "Not started")}</span>
        <small>${Number(item.word_count || 0).toLocaleString()} words</small>
      </button>`).join("");
    track.querySelectorAll("[data-cockpit-chapter]").forEach(button => button.addEventListener("click", () => {
      const chapter = Number(button.dataset.cockpitChapter || 1);
      focusChapterForDevelopment(chapter);
    }));
  }

  const tbody = $("objectiveMatrixBody");
  const matrix = data.objective_matrix || [];
  if (tbody) {
    tbody.innerHTML = matrix.map(row => `
      <tr>
        <td><strong>${Number(row.objective_number)}.</strong> ${escapeHtml(row.objective || "")}</td>
        <td>${escapeHtml(row.research_question || "Not mapped")}</td>
        <td>${escapeHtml(row.hypothesis || "Not mapped / not required")}</td>
        <td>${row.result_covered ? "✓ Trace found" : "—"}</td>
        <td>${row.conclusion_covered ? "✓ Trace found" : "—"}</td>
        <td><span class="logic-status ${escapeHtml(row.status || "needs_action")}">${escapeHtml(logicStatusLabel(row.status))}</span></td>
      </tr>`).join("");
  }
  if ($("objectiveMatrixEmpty")) $("objectiveMatrixEmpty").hidden = matrix.length > 0;

  const issues = data.issues || [];
  if ($("cockpitIssueCount")) $("cockpitIssueCount").textContent = String(issues.length);
  if ($("cockpitIssues")) {
    $("cockpitIssues").innerHTML = issues.length
      ? issues.map(item => `<div class="cockpit-issue ${escapeHtml(item.severity || "advisory")}"><strong>${escapeHtml((item.severity || "advisory").replace(/_/g, " "))}</strong><div>${escapeHtml(item.message || "")}</div></div>`).join("")
      : `<div class="cockpit-issue advisory">No deterministic alignment warning is currently detected. Supervisor and disciplinary review are still required.</div>`;
  }
}

async function refreshResearchCockpit() {
  const panel = $("researchCockpit");
  if (!currentProjectId) {
    if (panel) panel.hidden = true;
    return null;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/research-logic`);
    renderResearchCockpit(data);
    await refreshVersionHistory();
    return data;
  } catch (error) {
    if (panel) panel.hidden = false;
    if ($("cockpitNextActionMessage")) $("cockpitNextActionMessage").textContent = `Research logic could not refresh: ${error.message || error}`;
    return null;
  }
}

function focusChapterForDevelopment(chapterNumber) {
  const chapter = Number(chapterNumber || 1);
  if ($("chapterSelect")?.querySelector(`option[value="${chapter}"]`)) {
    $("chapterSelect").value = String(chapter);
    currentChapter = chapter;
    renderSections();
    updateChapterSpecificUi();
    refreshVersionHistory();
  }
  $("chapterSelect")?.scrollIntoView({behavior: "smooth", block: "center"});
}

function continueFromCockpit() {
  const button = $("cockpitNextActionBtn");
  const type = button?.dataset.actionType || currentResearchCockpit?.next_action?.type || "chapter";
  const chapter = Number(button?.dataset.chapterNumber || currentResearchCockpit?.next_action?.chapter_number || 1);
  if (type === "sources") {
    const target = $("sourceSearchQuery");
    const details = target?.closest("details");
    if (details) details.open = true;
    target?.scrollIntoView({behavior: "smooth", block: "center"});
    target?.focus();
    return;
  }
  if (type === "project_logic") {
    const target = !lines($("objectives")?.value || "").length ? $("objectives") : $("research_questions") || $("objectives");
    target?.scrollIntoView({behavior: "smooth", block: "center"});
    target?.focus();
    return;
  }
  focusChapterForDevelopment(chapter);
}

async function refreshVersionHistory() {
  const box = $("versionHistoryList");
  if (!box || !currentProjectId) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/versions/${Number(currentChapter || 1)}?limit=15`);
    const versions = data.versions || [];
    if (!versions.length) {
      box.innerHTML = `<p class="hint">No saved version yet for Chapter ${Number(currentChapter || 1)}. A snapshot is created after each successful draft or strengthening pass.</p>`;
      return;
    }
    box.innerHTML = versions.map(version => {
      const created = version.created_at ? new Date(version.created_at) : null;
      const dateText = created && !Number.isNaN(created.getTime()) ? created.toLocaleString() : String(version.created_at || "");
      return `<div class="version-row">
        <div><strong>Version ${Number(version.version_number)}</strong><div class="version-meta">${escapeHtml(version.label || version.source || "Chapter snapshot")} · ${Number(version.character_count || 0).toLocaleString()} characters · ${escapeHtml(dateText)}</div></div>
        <div class="version-actions"><button type="button" class="secondary-action" data-restore-version="${escapeHtml(version.id)}">Restore this version</button></div>
      </div>`;
    }).join("");
    box.querySelectorAll("[data-restore-version]").forEach(button => button.addEventListener("click", () => restoreChapterVersion(button.dataset.restoreVersion).catch(error => handleWorkspaceError(error, "draftStatus"))));
  } catch (error) {
    box.innerHTML = `<p class="hint">Version history could not be loaded: ${escapeHtml(error.message || error)}</p>`;
  }
}

async function restoreChapterVersion(versionId) {
  if (!currentProjectId || !versionId) return;
  const result = await api(`/api/projects/${encodeURIComponent(currentProjectId)}/versions/${Number(currentChapter || 1)}/${encodeURIComponent(versionId)}/restore`, {method: "POST"});
  $("draftOutput").value = result.draft || "";
  savedProjectDrafts[String(currentChapter)] = result.draft || "";
  currentClaimSupportReview = null;
  renderDraftPreview(result.draft || "");
  if ($("draftStatus")) $("draftStatus").textContent = `Version ${result.restored_from} restored as a new recoverable snapshot. Claim support will be re-audited before export.`;
  await refreshClaimSupportReview();
  await refreshResearchCockpit();
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
  let safe = escapeHtml(value || "");
  for (const item of (currentClaimSupportReview?.claims || [])) {
    if (item.status === 'resolved') continue;
    const target = escapeHtml(item.claim_text || '');
    if (target && safe.includes(target)) safe = safe.replace(target, `<span class="unsupported-claim-highlight" title="Claim needs verified source support">${target}</span>`);
  }
  const withAdditions = safe.replace(/\[\[ADD\]\]/g, '<span class="addition-text">').replace(/\[\[\/ADD\]\]/g, '</span>');
  preview.innerHTML = withAdditions.replace(/(\[[^\]\n]{3,}\])/g, '<span class="placeholder-text">$1</span>');
}

function syncOptionalMasterToggle() {
  const groups = Array.from(document.querySelectorAll("details[data-optional-group]"));
  const button = $("toggleOptionalFieldsBtn");
  if (!button || !groups.length) return;
  const allOpen = groups.every(group => group.open);
  button.textContent = allOpen ? "Show less" : "Show more optional fields";
  button.setAttribute("aria-expanded", allOpen ? "true" : "false");
}

function initialiseOptionalFields() {
  const groups = Array.from(document.querySelectorAll("details[data-optional-group]"));
  groups.forEach(group => group.addEventListener("toggle", syncOptionalMasterToggle));
  $("toggleOptionalFieldsBtn")?.addEventListener("click", () => {
    const open = !groups.every(group => group.open);
    groups.forEach(group => { group.open = open; });
    syncOptionalMasterToggle();
  });
  syncOptionalMasterToggle();
}

function download(path) {
  window.location.href = path;
}

if ($("draftOutput")) {
  $("draftOutput").addEventListener("input", () => {
    if (currentClaimSupportReview) {
      currentClaimSupportReview.final_output_ready = false;
      currentClaimSupportReview.status = "stale_after_manual_edit";
      if ($("claimSupportStatus")) $("claimSupportStatus").textContent = "The chapter was edited after the last evidence audit. Re-run Claim Support Review before export.";
      setClaimReviewExportGate();
    }
    renderDraftPreview($("draftOutput").value);
  });
}


$("workspaceUnlockBtn")?.addEventListener("click", () => $("unlockChapterBtn")?.click());
$("applyWorkspaceComplimentaryBtn")?.addEventListener("click", () => applyWorkspaceComplimentaryAccess().catch(err => { if ($("workspaceComplimentaryStatus")) $("workspaceComplimentaryStatus").textContent = err.message || "Token could not be applied."; }));
$("clearWorkspaceComplimentaryBtn")?.addEventListener("click", () => clearWorkspaceComplimentaryAccess().catch(() => {}));
document.addEventListener("input", (event) => { if (event.target?.closest?.(".workspace-guided-frame")) updateWorkspaceFlow(); });
document.addEventListener("change", (event) => { if (event.target?.closest?.(".workspace-guided-frame")) { updateWorkspaceFlow(); refreshWorkspaceAccessStatus().catch(() => {}); } });
window.addEventListener("projectready:session-ready", () => refreshWorkspaceAccessStatus().catch(() => {}));
$("applyApprovedClaimSourcesBtn")?.addEventListener("click", () => applyApprovedClaimSources().catch(err => { if ($("claimSupportStatus")) $("claimSupportStatus").textContent = err.message || "Approved citations could not be applied."; }));
$("refreshClaimSupportReviewBtn")?.addEventListener("click", () => refreshClaimSupportReview().catch(err => { if ($("claimSupportStatus")) $("claimSupportStatus").textContent = err.message || "Claim-support review could not be refreshed."; }));
$("createProjectBtn").addEventListener("click", () => createProject().catch(err => handleWorkspaceError(err, "projectStatus")));
if ($("saveProjectProfileBtn")) $("saveProjectProfileBtn").addEventListener("click", () => saveCurrentProjectProfile().catch(err => handleWorkspaceError(err, "projectStatus")));
if ($("refreshCockpitBtn")) $("refreshCockpitBtn").addEventListener("click", () => refreshResearchCockpit().catch(err => handleWorkspaceError(err, "projectStatus")));
if ($("cockpitNextActionBtn")) $("cockpitNextActionBtn").addEventListener("click", continueFromCockpit);
if ($("refreshVersionsBtn")) $("refreshVersionsBtn").addEventListener("click", () => refreshVersionHistory().catch(err => handleWorkspaceError(err, "draftStatus")));
if ($("saveRecoveryBtn")) $("saveRecoveryBtn").addEventListener("click", () => saveCurrentProjectRecovery().catch(err => handleWorkspaceError(err, "projectStatus")));
if ($("recoverProjectBtn")) $("recoverProjectBtn").addEventListener("click", () => recoverWorkspaceProjects().catch(err => handleWorkspaceError(err, "projectStatus")));
$("draftBtn").addEventListener("click", () => generateDraft().catch(err => handleWorkspaceError(err, "draftStatus")));
if ($("saveContinuationChangesBtn")) $("saveContinuationChangesBtn").addEventListener("click", () => saveContinuationChanges().catch(err => handleWorkspaceError(err, "continuationSaveStatus")));
if ($("continueNextChapterBtn")) $("continueNextChapterBtn").addEventListener("click", () => continueToNextChapter().catch(err => handleWorkspaceError(err, "continuationSaveStatus")));
if ($("stayCurrentChapterBtn")) $("stayCurrentChapterBtn").addEventListener("click", () => { if ($("chapterContinuationPanel")) $("chapterContinuationPanel").hidden = true; });
if ($("cancelBackgroundJobBtn")) $("cancelBackgroundJobBtn").addEventListener("click", () => cancelActiveBackgroundJob().catch(err => handleWorkspaceError(err, "draftStatus")));
const clearWorkspaceButton = ensureWorkspaceClearButton();
if (clearWorkspaceButton) clearWorkspaceButton.addEventListener("click", () => clearWorkspaceAndStartNewJob().catch(err => handleWorkspaceError(err, "projectStatus")));
if ($("pageTargetMode")) $("pageTargetMode").addEventListener("change", updateCustomPageTargetFromInputs);
if ($("customPageMin")) $("customPageMin").addEventListener("input", updateCustomPageTargetFromInputs);
if ($("customPageMax")) $("customPageMax").addEventListener("input", updateCustomPageTargetFromInputs);
if ($("chapterOneAutofillBtn")) $("chapterOneAutofillBtn").addEventListener("click", () => autofillFromChapterOneUpload().catch(err => handleWorkspaceError(err, "chapterOneAutofillStatus")));
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
if ($("uploadSelectedPapersBtn")) {
  $("uploadSelectedPapersBtn").addEventListener("click", () => uploadSelectedPapers().catch(err => handleWorkspaceError(err, "selectedPapersStatus")));
}
$("checkBtn").addEventListener("click", () => runCheck().then(updatePaymentPanel).catch(err => handleWorkspaceError(err, "draftStatus")));
$("downloadDraftBtn").addEventListener("click", () => {
  protectedDownload(`/api/projects/${currentProjectId}/export/chapter/${currentChapter}`, currentChapter)
    .then(updatePaymentPanel)
    .catch(err => handleWorkspaceError(err, "draftStatus"));
});
$("downloadCheckBtn").addEventListener("click", () => download(`/api/projects/${currentProjectId}/export/check/${currentChapter}`));
if ($("downloadProjectBtn")) $("downloadProjectBtn").addEventListener("click", () => {
  if (!currentProjectId) return handleWorkspaceError(new Error("Create or restore a project first."), "draftStatus");
  download(`/api/projects/${currentProjectId}/export/project-working-file`);
});
if ($("unlockChapterBtn")) $("unlockChapterBtn").addEventListener("click", () => openCurrentCheckout().catch(err => handleWorkspaceError(err, "chapterAccessStatus")));
if ($("accessPayBtn")) $("accessPayBtn").addEventListener("click", () => openCurrentCheckout({direct: true}).catch(err => handleWorkspaceError(err, "draftStatus")));
if ($("accessDismissBtn")) $("accessDismissBtn").addEventListener("click", hideAccessRequiredNotice);
if ($("revisionMode")) $("revisionMode").addEventListener("change", updatePaymentPanel);
if ($("citationDisciplineMatrix")) $("citationDisciplineMatrix").addEventListener("change", () => { if (currentProjectId) saveCurrentProjectProfile().catch(() => {}); });
if ($("level")) {
  $("level").addEventListener("change", () => { updateLevelHint(); updatePaymentPanel(); });
  updateLevelHint();
}

updateChapterSpecificUi();

async function initialiseWorkspace() {
  ensureWorkspaceClearButton();
  const params = new URLSearchParams(window.location.search);
  const explicitNewJob = params.get(WORKSPACE_NEW_JOB_PARAM) === "1";
  if (explicitNewJob) clearWorkspaceStoredJobState();
  prefillRecoveryEmail();
  const returnedProject = explicitNewJob ? "" : (params.get("project_id") || "");
  if (returnedProject) {
    currentProjectId = returnedProject;
    localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, returnedProject);
  }
  if (window.ProjectReadySessionBootstrap?.ready) await window.ProjectReadySessionBootstrap.ready;
  await loadTemplate();
  await refreshWorkspaceAccessStatus();
  updateWorkspaceFlow();
  if (explicitNewJob) {
    resetWorkspaceBrowserFields();
    prefillRecoveryEmail();
  } else {
    await restoreCurrentProject();
  }
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
    const handoff = params.get("handoff") || "";
    let restoreMessage = "Payment confirmed. Your chapter access is ready.";
    if (handoff && window.ProjectReadyPayments?.redeemPaymentHandoff) {
      try {
        const restored = await ProjectReadyPayments.redeemPaymentHandoff(handoff);
        restoreMessage = "Payment confirmed and paid access restored on this device.";
        if (restored.project_id) {
          currentProjectId = restored.project_id;
          localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, restored.project_id);
        }
        if (restored.chapter_number && $("chapterSelect")?.querySelector(`option[value="${restored.chapter_number}"]`)) {
          $("chapterSelect").value = String(restored.chapter_number);
          currentChapter = Number(restored.chapter_number);
          renderSections();
        }
      } catch (error) {
        restoreMessage = `Payment confirmed, but automatic access restoration needs your email and Purchase ID. ${error.message || ""}`.trim();
      }
    } else if (params.get("handoff_status") === "recovery_required") {
      restoreMessage = "Payment confirmed. Use the Restore paid access option with your payment email and Purchase ID to recover the remaining entitlements.";
    }
    if ($("planNotice")) {
      $("planNotice").hidden = false;
      $("planNotice").textContent = restoreMessage;
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
  if (payment || registered || explicitNewJob) {
    const clean = new URL(window.location.pathname, window.location.origin);
    if (currentProjectId) clean.searchParams.set("project_id", currentProjectId);
    if (currentChapter) clean.searchParams.set("chapter", String(currentChapter));
    history.replaceState({}, document.title, clean.pathname + clean.search);
  }
  ensureWorkspaceClearButton();
  await updatePaymentPanel();
}

ensureWorkspaceClearButton();
initialiseOptionalFields();
initialiseWorkspace().then(resumeBackgroundDraftIfAvailable).catch(err => {
  document.body.innerHTML = `<pre>Failed to load app: ${escapeHtml(err.message)}</pre>`;
});

