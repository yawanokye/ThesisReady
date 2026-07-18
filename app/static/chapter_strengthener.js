const byId = (id) => document.getElementById(id);

const form = byId('revisionForm');
const chapterText = byId('chapterText');
const supervisorComments = byId('supervisorComments');
const previousChaptersContext = byId('previousChaptersContext');
const revisedChapter = byId('revisedChapter');
const strengtheningReport = byId('strengtheningReport');
const supervisorMatrix = byId('supervisorMatrix');
const supervisorMatrixPanel = byId('supervisorMatrixPanel');
const statusBox = byId('status');
const uploadStatus = byId('uploadStatus');
const reviseBtn = byId('reviseBtn');
const copyChapterBtn = byId('copyChapterBtn');
const copyReportBtn = byId('copyReportBtn');
const copyMatrixBtn = byId('copyMatrixBtn');
const downloadRevisionBtn = byId('downloadRevisionBtn');
const revisionMeta = byId('revisionMeta');
const targetNote = byId('targetNote');
const PROJECT_STORAGE_KEY = 'projectready-current-project';
const STRENGTHENER_NEW_JOB_PARAM = 'new_job';


function strengthenerPagePath() {
  const internalPath = window.ProjectReadyInternalPortal?.modulePath;
  if (internalPath) return String(internalPath).replace(/\/$/, '');
  const current = String(window.location.pathname || '');
  if (/^\/internal\//.test(current) && /\/chapter-strengthener$/.test(current)) return current.replace(/\/$/, '');
  return '/chapter-strengthener';
}

function isInternalDeveloperCredential(credential) {
  return String(credential?.purchase_id || '').startsWith('pr-internal-v1:');
}

function clearStrengthenerStoredJobState() {
  currentProject = null;
  activeStrengthenerJob = null;
  for (const storage of [sessionStorage, localStorage]) {
    try { storage.removeItem(PROJECT_STORAGE_KEY); } catch (_error) {}
    try {
      Object.keys(storage)
        .filter((key) => key.startsWith('projectready-strengthener-job:'))
        .forEach((key) => storage.removeItem(key));
    } catch (_error) {}
  }
}

function prefillStrengthenerRecoveryEmails() {
  const profile = window.ProjectReadyPayments?.readRegistrationProfile?.();
  if (profile?.email) {
    if (!byId('recoverEmail').value) byId('recoverEmail').value = profile.email;
    if (!byId('externalRecoveryEmail').value) byId('externalRecoveryEmail').value = profile.email;
  }
}

function resetStrengthenerForNewJob() {
  form.reset();
  document.querySelectorAll('#revisionForm input[type="file"]').forEach((input) => { input.value = ''; });
  byId('projectId').value = '';
  chapterText.value = '';
  supervisorComments.value = '';
  if (previousChaptersContext) previousChaptersContext.value = '';
  revisedChapter.value = '';
  strengtheningReport.value = '';
  supervisorMatrix.value = '';
  supervisorMatrixPanel.hidden = true;
  lastResult = null;
  currentProject = null;
  customNewSections = [];
  activeStrengthenerJob = null;
  strengthenerJobInFlight = false;
  renderStrengthenerJob(null);
  renderCustomNewSections();
  renderStrengthenerSections();
  if (byId('customTargetPagesFields')) byId('customTargetPagesFields').hidden = true;
  revisionMeta.textContent = 'Revision details will appear here.';
  uploadStatus.textContent = '';
  byId('projectConnectionStatus').textContent = 'No project is connected. Select an existing project or bring a new chapter.';
  byId('externalProjectStatus').textContent = '';
  byId('recoveryResults').innerHTML = '';
  byId('useSavedDraftBtn').disabled = true;
  message('Old chapter entries were cleared. Complete the new strengthening job to begin.');
  enableOutputs(false);
  copyMatrixBtn.disabled = true;
  setSourceMode('existing');
  updateTargetNote();
  prefillStrengthenerRecoveryEmails();
}

async function clearStrengthenerAndStartNewJob() {
  if (activeStrengthenerJob && ['queued', 'retrying'].includes(activeStrengthenerJob.job?.status)) {
    try { await cancelActiveStrengthenerJob(); } catch (_error) {}
  }
  clearStrengthenerStoredJobState();
  const clean = new URL(strengthenerPagePath(), window.location.origin);
  clean.searchParams.set(STRENGTHENER_NEW_JOB_PARAM, '1');
  clean.searchParams.set('_', String(Date.now()));
  window.location.replace(clean.pathname + clean.search);
}

let currentProject = null;
let lastResult = null;
let strengthenerTemplate = null;
let customNewSections = [];
let activeStrengthenerJob = null;
let strengthenerJobInFlight = false;

function message(text, kind = '') {
  statusBox.textContent = text || '';
  statusBox.className = `status ${kind}`.trim();
}

function setBusy(busy) {
  reviseBtn.disabled = busy;
  reviseBtn.textContent = busy ? 'Background request running…' : 'Strengthen my working chapter';
}

function selectedSourceMode() {
  return document.querySelector('input[name="chapterSource"]:checked')?.value || 'existing';
}

function setSourceMode(mode) {
  const target = mode === 'external' ? 'external' : 'existing';
  const radio = document.querySelector(`input[name="chapterSource"][value="${target}"]`);
  if (radio) radio.checked = true;
  byId('existingProjectPanel').hidden = target !== 'existing';
  byId('externalProjectPanel').hidden = target !== 'external';
  updateAccessSummary();
}

document.querySelectorAll('input[name="chapterSource"]').forEach((radio) => {
  radio.addEventListener('change', () => setSourceMode(radio.value));
});

async function extractFile(fileInput, target, label) {
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    uploadStatus.textContent = `Choose a ${label} file first.`;
    return;
  }
  const body = new FormData();
  body.append('file', file);
  uploadStatus.textContent = `Extracting ${file.name}…`;
  try {
    const response = await fetch('/api/chapter-strengthener/extract-file', { method: 'POST', body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'File extraction failed.');
    target.value = target.value.trim() ? `${target.value.trim()}\n\n${data.text}` : data.text;
    uploadStatus.textContent = `${file.name} extracted, ${Number(data.character_count || 0).toLocaleString()} characters${data.truncated ? ', truncated to the extraction limit' : ''}.`;
  } catch (error) {
    uploadStatus.textContent = error.message || 'File extraction failed.';
  }
}

byId('extractChapterBtn').addEventListener('click', () => extractFile(byId('chapterFile'), chapterText, 'chapter'));
byId('extractCommentsBtn').addEventListener('click', () => extractFile(byId('commentsFile'), supervisorComments, 'supervisor-comment'));
byId('extractAlignmentBtn').addEventListener('click', () => extractFile(byId('alignmentFile'), previousChaptersContext, 'previous-chapter or complete-work'));

function selectedSectionPayload() {
  const strengthen = Array.from(document.querySelectorAll('.section-strengthen:checked')).map((input) => ({
    id: input.dataset.sectionId || '',
    title: input.dataset.sectionTitle || '',
  }));
  const add = Array.from(document.querySelectorAll('.section-add:checked')).map((input) => ({
    id: input.dataset.sectionId || '',
    title: input.dataset.sectionTitle || '',
  }));
  return { strengthen, add };
}

function updateSectionSelectionCount() {
  const { strengthen, add } = selectedSectionPayload();
  const count = strengthen.length + add.length + customNewSections.length;
  const badge = byId('sectionSelectionCount');
  if (badge) badge.textContent = `${count} selected`;
  updateTargetNote();
}

function renderCustomNewSections() {
  const box = byId('customNewSectionsList');
  if (!box) return;
  box.innerHTML = '';
  customNewSections.forEach((section, index) => {
    const row = document.createElement('div');
    row.className = 'custom-section-row';
    const text = document.createElement('div');
    text.innerHTML = `<strong>${section.title}</strong>${section.instructions ? `<small>${section.instructions}</small>` : ''}`;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'ghost-button compact-remove';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => {
      customNewSections.splice(index, 1);
      renderCustomNewSections();
      updateSectionSelectionCount();
    });
    row.append(text, remove);
    box.appendChild(row);
  });
}

function chapterTemplateNumber() {
  return chapterNumber();
}

function renderStrengthenerSections() {
  const box = byId('strengthenerSectionsBox');
  if (!box) return;
  const chapter = strengthenerTemplate?.chapters?.find((item) => Number(item.chapter_number) === chapterTemplateNumber());
  const sections = chapter?.section_groups?.flatMap((group) => group.sections || []) || [];
  box.innerHTML = '';
  if (!sections.length) {
    box.innerHTML = '<p class="help">No standard section list is available for this custom chapter. Add one or more custom new sections below, or strengthen the complete chapter.</p>';
    updateSectionSelectionCount();
    return;
  }
  sections.forEach((section) => {
    const row = document.createElement('div');
    row.className = 'strengthener-section-row';
    const title = document.createElement('div');
    title.className = 'strengthener-section-title';
    title.innerHTML = `<strong>${section.section_title}</strong>${section.rules?.[0] ? `<small>${section.rules[0]}</small>` : ''}`;
    const strengthenLabel = document.createElement('label');
    strengthenLabel.className = 'section-action-check';
    const strengthen = document.createElement('input');
    strengthen.type = 'checkbox';
    strengthen.className = 'section-strengthen';
    strengthen.dataset.sectionId = section.section_id;
    strengthen.dataset.sectionTitle = section.section_title;
    strengthenLabel.append(strengthen, document.createTextNode(' Strengthen'));
    const addLabel = document.createElement('label');
    addLabel.className = 'section-action-check';
    const add = document.createElement('input');
    add.type = 'checkbox';
    add.className = 'section-add';
    add.dataset.sectionId = section.section_id;
    add.dataset.sectionTitle = section.section_title;
    addLabel.append(add, document.createTextNode(' Add'));
    strengthen.addEventListener('change', () => {
      if (strengthen.checked) add.checked = false;
      updateSectionSelectionCount();
    });
    add.addEventListener('change', () => {
      if (add.checked) strengthen.checked = false;
      updateSectionSelectionCount();
    });
    row.append(title, strengthenLabel, addLabel);
    box.appendChild(row);
  });
  updateSectionSelectionCount();
}

async function loadStrengthenerTemplate() {
  try {
    const response = await fetch('/static/default_template.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('Template could not be loaded.');
    strengthenerTemplate = await response.json();
  } catch (_error) {
    strengthenerTemplate = { chapters: [] };
  }
  renderStrengthenerSections();
}

function customTargetPayload() {
  const enabled = Boolean(byId('customTargetPagesEnabled')?.checked);
  return {
    custom_target_pages_enabled: enabled,
    target_page_min: enabled ? Number(byId('targetPageMin')?.value || 0) || null : null,
    target_page_max: enabled ? Number(byId('targetPageMax')?.value || 0) || null : null,
  };
}

async function updateTargetNote() {
  try {
    const { strengthen, add } = selectedSectionPayload();
    const response = await fetch('/api/chapter-strengthener/targets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        academic_level: byId('academicLevel').value,
        chapter_type: byId('chapterType').value,
        strengthening_scope: byId('strengtheningScope')?.value || 'whole_chapter',
        selected_section_count: strengthen.length + add.length + customNewSections.length,
        ...customTargetPayload(),
      }),
    });
    const data = await response.json();
    if (!response.ok) return;
    const scopeLabel = data.strengthening_scope === 'selected_sections' ? 'selected-section output' : 'complete selected chapter';
    targetNote.textContent = `Planning target for the ${scopeLabel}: ${data.page_range.minimum}-${data.page_range.maximum} pages, approximately ${Number(data.word_range_estimate.minimum).toLocaleString()}-${Number(data.word_range_estimate.maximum).toLocaleString()} words, and ${data.citation_density_per_1000_words.minimum}-${data.citation_density_per_1000_words.maximum} citation occurrences per 1,000 words.${data.custom_target_applied ? ' Custom page target applied.' : ''}`;
    if (!byId('customTargetPagesEnabled')?.checked) {
      if (byId('targetPageMin')) byId('targetPageMin').placeholder = String(data.page_range.minimum);
      if (byId('targetPageMax')) byId('targetPageMax').placeholder = String(data.page_range.maximum);
    }
  } catch (_error) {
    targetNote.textContent = 'Planning target unavailable.';
  }
}

byId('academicLevel').addEventListener('change', () => {
  updateTargetNote();
  updateAccessSummary();
});
byId('chapterType').addEventListener('change', () => {
  renderStrengthenerSections();
  updateTargetNote();
  updateAccessSummary();
});
byId('strengtheningScope')?.addEventListener('change', updateTargetNote);
byId('customTargetPagesEnabled')?.addEventListener('change', () => {
  byId('customTargetPagesFields').hidden = !byId('customTargetPagesEnabled').checked;
  updateTargetNote();
});
byId('targetPageMin')?.addEventListener('input', updateTargetNote);
byId('targetPageMax')?.addEventListener('input', updateTargetNote);
byId('addCustomNewSectionBtn')?.addEventListener('click', () => {
  const title = byId('customNewSectionTitle').value.trim();
  const instructions = byId('customNewSectionInstructions').value.trim();
  if (!title) {
    message('Enter a title for the new section before adding it.', 'error');
    return;
  }
  customNewSections.push({ title, instructions });
  byId('customNewSectionTitle').value = '';
  byId('customNewSectionInstructions').value = '';
  renderCustomNewSections();
  updateSectionSelectionCount();
});
loadStrengthenerTemplate();
updateTargetNote();

function payloadFromForm() {
  return {
    thesis_title: byId('thesisTitle').value.trim(),
    chapter_title: byId('chapterTitle').value.trim(),
    chapter_type: byId('chapterType').value,
    chapter_text: chapterText.value.trim(),
    academic_level: byId('academicLevel').value,
    discipline: byId('discipline').value.trim(),
    study_stage: byId('studyStage').value,
    research_area: byId('researchArea').value.trim(),
    context: byId('context').value.trim(),
    objectives: byId('objectives').value.trim(),
    research_questions: byId('researchQuestions').value.trim(),
    hypotheses: byId('hypotheses').value.trim(),
    theory_framework: byId('theoryFramework').value.trim(),
    variables_constructs: byId('variablesConstructs').value.trim(),
    methodology: byId('methodology').value.trim(),
    data_and_results: byId('dataResults').value.trim(),
    contribution_claim: byId('contributionClaim').value.trim(),
    school_guidelines: byId('schoolGuidelines').value.trim(),
    background_structure: byId('strengthenerBackgroundStructure') ? byId('strengthenerBackgroundStructure').value : 'continuous_narrative',
    purpose_statement_style: byId('strengthenerPurposeStyle') ? byId('strengthenerPurposeStyle').value : 'concise_general_objective',
    citation_style: byId('citationStyle').value,
    revision_level: byId('revisionLevel').value,
    humanizer_mode: byId('strengthenerHumanizerMode') ? byId('strengthenerHumanizerMode').value : 'balanced',
    revision_goals: byId('revisionGoals').value.trim(),
    supervisor_comments: supervisorComments.value.trim(),
    previous_chapters_context: previousChaptersContext ? previousChaptersContext.value.trim() : '',
    uploaded_content_scope: byId('uploadedContentScope')?.value || 'selected_chapter',
    strengthening_scope: byId('strengtheningScope')?.value || 'whole_chapter',
    selected_section_ids: selectedSectionPayload().strengthen.map((item) => item.id),
    selected_section_titles: selectedSectionPayload().strengthen.map((item) => item.title),
    new_section_ids: selectedSectionPayload().add.map((item) => item.id),
    new_section_titles: selectedSectionPayload().add.map((item) => item.title),
    custom_new_sections: customNewSections,
    ...customTargetPayload(),
    strengthen_structure: byId('strengthenStructure').checked,
    allow_missing_section_insertions: byId('allowMissingSectionInsertions') ? byId('allowMissingSectionInsertions').checked : true,
    strengthen_problem_gap: byId('strengthenProblemGap').checked,
    strengthen_conceptualisation: byId('strengthenConceptualisation').checked,
    increase_citation_density: byId('increaseCitationDensity').checked,
    assess_method_fit: byId('assessMethodFit').checked,
    assess_results: byId('assessResults').checked,
    deepen_discussion: byId('deepenDiscussion').checked,
    strengthen_conclusions: byId('strengthenConclusions').checked,
    improve_language: byId('improveLanguage').checked,
    include_supervisor_response_matrix: byId('includeResponseMatrix').checked,
    include_source_search: byId('includeSourceSearch').checked,
    include_older_foundational: byId('includeOlderFoundational').checked,
    source_search_terms: byId('sourceSearchTerms').value.trim(),
    source_limit: 45,
    source_bank: Array.isArray(currentProject?.profile?.source_bank) ? currentProject.profile.source_bank : [],
    save_to_project: byId('saveToProject').checked,
    academic_integrity_confirmed: byId('strengthenerIntegrityDeclaration').checked,
    user_contribution_confirmed: byId('strengthenerContributionDeclaration').checked,
  };
}

function requestId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
  return `pr-strengthen-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function chapterNumber() {
  const match = String(byId('chapterType').value || '').match(/^[1-5]/);
  return match ? Number(match[0]) : 6;
}

function projectId() {
  const value = byId('projectId').value.trim();
  if (
    selectedSourceMode() === 'external'
    && currentProject?.profile?.project_kind !== 'external_revision'
  ) {
    return '';
  }
  return value;
}

function isRevisionOnlyProject() {
  return currentProject?.profile?.project_kind === 'external_revision' || selectedSourceMode() === 'external';
}

function paymentHeaders() {
  if (!window.ProjectReadyPayments || !projectId()) return {};
  return ProjectReadyPayments.paymentHeaders(projectId(), chapterNumber(), 'chapter_strengthener');
}

function accessOptions() {
  return {
    projectId: projectId(),
    chapterNumber: chapterNumber(),
    chapterTitle: byId('chapterTitle').value.trim() || byId('chapterType').value,
    academicLevel: byId('academicLevel').value,
    purchaseMode: isRevisionOnlyProject() ? 'revision_only' : 'chapter',
    customerEmail: isRevisionOnlyProject() ? byId('externalRecoveryEmail').value.trim() : byId('recoverEmail').value.trim(),
    returnPath: `${strengthenerPagePath()}?project_id=${encodeURIComponent(projectId())}`,
  };
}

async function handleProtectedError(response, data, fallbackMessage) {
  const detail = data?.detail;
  const errorMessage = typeof detail === 'string' ? detail : (detail?.message || fallbackMessage);
  if ([401, 402].includes(Number(response.status)) && window.ProjectReadyPayments && projectId()) {
    message(errorMessage, 'error');
    try {
      const gateMessage = isRevisionOnlyProject()
        ? 'This uploaded chapter requires a revision-only purchase before strengthening can begin.'
        : 'Chapter strengthening uses the revision included with the paid chapter.';
      await ProjectReadyPayments.openAccessGate(accessOptions(), detail || { message: gateMessage });
    } catch (_error) {}
  }
  throw new Error(errorMessage);
}

function normaliseLevel(value) {
  const aliases = {
    'Research Masters (e.g. MPhil)': 'Research Masters / MPhil',
    'Professional Doctorate (e.g. DBA, DEd)': 'Professional Doctorate / DBA / DEd',
    'Professional Doctorate': 'Professional Doctorate / DBA / DEd',
  };
  return aliases[value] || value || 'Bachelors';
}

function asLines(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join('\n');
  if (value && typeof value === 'object') {
    if (Array.isArray(value.raw_variables)) return value.raw_variables.filter(Boolean).join('\n');
    return Object.entries(value).map(([key, item]) => `${key}: ${item}`).join('\n');
  }
  return String(value || '');
}

function fillFromProject(project) {
  currentProject = project;
  const profile = project.profile || {};
  byId('projectId').value = project.id || '';
  byId('thesisTitle').value = project.title || profile.title || byId('thesisTitle').value;
  byId('academicLevel').value = normaliseLevel(profile.level);
  byId('discipline').value = profile.programme || profile.department || byId('discipline').value;
  byId('researchArea').value = profile.research_area || byId('researchArea').value;
  byId('context').value = profile.study_context || byId('context').value;
  byId('objectives').value = asLines(profile.objectives) || byId('objectives').value;
  byId('researchQuestions').value = asLines(profile.research_questions) || byId('researchQuestions').value;
  byId('hypotheses').value = asLines(profile.hypotheses) || byId('hypotheses').value;
  byId('variablesConstructs').value = asLines(profile.variables) || byId('variablesConstructs').value;
  byId('methodology').value = profile.research_approach || byId('methodology').value;
  byId('schoolGuidelines').value = profile.format_notes || byId('schoolGuidelines').value;
  if (byId('strengthenerBackgroundStructure')) byId('strengthenerBackgroundStructure').value = profile.background_structure || 'continuous_narrative';
  if (byId('strengthenerPurposeStyle')) byId('strengthenerPurposeStyle').value = profile.purpose_statement_style || 'concise_general_objective';
  byId('sourceSearchTerms').value = profile.source_search_terms || byId('sourceSearchTerms').value;
  byId('studyStage').value = profile.study_stage || byId('studyStage').value;
  byId('theoryFramework').value = profile.theory_framework || byId('theoryFramework').value;
  byId('contributionClaim').value = profile.contribution_claim || byId('contributionClaim').value;
  byId('dataResults').value = profile.data_and_results || byId('dataResults').value;
  if (previousChaptersContext && profile.previous_chapters_context && typeof profile.previous_chapters_context === 'string') {
    previousChaptersContext.value = profile.previous_chapters_context;
  }
  if (byId('allowMissingSectionInsertions') && profile.allow_missing_section_insertions !== undefined) {
    byId('allowMissingSectionInsertions').checked = Boolean(profile.allow_missing_section_insertions);
  }
  if (profile.citation_style) byId('citationStyle').value = profile.citation_style;
  if (byId('strengthenerHumanizerMode') && profile.humanizer_mode) byId('strengthenerHumanizerMode').value = profile.humanizer_mode;
  if (profile.external_revision_chapter_type) byId('chapterType').value = profile.external_revision_chapter_type;
  if (profile.external_revision_chapter_title) byId('chapterTitle').value = profile.external_revision_chapter_title;
  if (byId('uploadedContentScope') && profile.uploaded_content_scope) byId('uploadedContentScope').value = profile.uploaded_content_scope;
  if (byId('strengtheningScope') && profile.strengthening_scope) byId('strengtheningScope').value = profile.strengthening_scope;
  if (byId('customTargetPagesEnabled')) byId('customTargetPagesEnabled').checked = Boolean(profile.custom_target_pages_enabled);
  if (byId('customTargetPagesFields')) byId('customTargetPagesFields').hidden = !Boolean(profile.custom_target_pages_enabled);
  if (byId('targetPageMin') && profile.target_page_min) byId('targetPageMin').value = profile.target_page_min;
  if (byId('targetPageMax') && profile.target_page_max) byId('targetPageMax').value = profile.target_page_max;
  customNewSections = Array.isArray(profile.custom_new_sections) ? profile.custom_new_sections : customNewSections;
  renderCustomNewSections();
  renderStrengthenerSections();

  localStorage.setItem(PROJECT_STORAGE_KEY, project.id);
  const external = profile.project_kind === 'external_revision';
  if (external) {
    setSourceMode('external');
    byId('externalProjectStatus').textContent = `Revision-only project created and connected: ${project.title || 'Untitled project'} (${project.id}).`;
    const draft = project.drafts?.[String(profile.external_revision_chapter_number || chapterNumber())] || '';
    if (draft.trim()) chapterText.value = draft;
  } else {
    setSourceMode('existing');
    byId('projectConnectionStatus').textContent = `Connected to ${project.title || 'ProjectReady AI project'} (${project.id}). Project details and attached source records have been loaded.`;
  }
  byId('useSavedDraftBtn').disabled = false;
  updateTargetNote();
  updateAccessSummary();
}

async function loadProject(explicitId = '') {
  const id = explicitId || projectId() || new URLSearchParams(window.location.search).get('project_id') || localStorage.getItem(PROJECT_STORAGE_KEY) || '';
  if (!id) {
    byId('projectConnectionStatus').textContent = 'No current project was found. Create or recover a project, or choose the option to bring your own chapter.';
    return;
  }
  byId('projectConnectionStatus').textContent = 'Loading project…';
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(id)}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Project could not be loaded.');
    fillFromProject(data);
  } catch (error) {
    currentProject = null;
    byId('projectConnectionStatus').textContent = error.message || 'Project could not be loaded.';
  }
}

async function createExternalRevisionProject(payload) {
  const email = byId('externalRecoveryEmail').value.trim();
  const pin = byId('externalRecoveryPin').value.trim();
  if (!email || !/^\d{6}$/.test(pin)) {
    throw new Error('Enter a valid recovery email and create a 6-digit recovery PIN.');
  }
  const response = await fetch('/api/chapter-strengthener/external-projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      recovery_email: email,
      recovery_pin: pin,
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'The revision-only project could not be created.');
  fillFromProject(data);
  return data;
}

async function updateAccessSummary() {
  const box = byId('chapterAccessSummary');
  await Promise.resolve(window.ProjectReadySessionBootstrap?.ready).catch(() => null);
  if (!projectId()) {
    box.textContent = selectedSourceMode() === 'external'
      ? 'Complete the chapter details and click Strengthen chapter. The app will create a recoverable revision-only project before checkout.'
      : 'Connect or recover a project before strengthening. A paid chapter includes one strengthening revision and one DOCX export.';
    return;
  }
  const credential = window.ProjectReadyPayments?.getCredential(projectId(), chapterNumber(), 'chapter_strengthener');
  if (isInternalDeveloperCredential(credential)) {
    box.textContent = 'Internal developer access is active for Chapter Strengthener. No payment quota will be consumed.';
    return;
  }
  if (!credential) {
    const label = isRevisionOnlyProject() ? 'Unlock revision-only access' : 'Unlock chapter';
    const explanation = isRevisionOnlyProject()
      ? 'This external chapter uses a revision-only plan with one strengthening revision, one compliance check and one DOCX export.'
      : 'Chapter strengthening uses the revision included with a paid chapter.';
    box.innerHTML = `${explanation} <button type="button" id="unlockStrengthenerChapter">${label}</button>`;
    byId('unlockStrengthenerChapter')?.addEventListener('click', () => ProjectReadyPayments.openAccessGate(accessOptions(), { message: explanation }));
    return;
  }
  try {
    const entitlement = await ProjectReadyPayments.checkEntitlement(projectId(), chapterNumber(), 'chapter_strengthener');
    const remaining = entitlement.remaining || {};
    if (entitlement.allowed) {
      box.textContent = `Payment confirmed. Remaining revision: ${remaining.revision ?? 0}. Remaining compliance check: ${remaining.compliance ?? 0}. Remaining export: ${remaining.export ?? 0}.`;
    } else {
      box.innerHTML = `${entitlement.message || 'Chapter access is not available.'} <button type="button" id="unlockStrengthenerChapter">Review access</button>`;
      byId('unlockStrengthenerChapter')?.addEventListener('click', () => ProjectReadyPayments.openAccessGate(accessOptions(), entitlement));
    }
  } catch (_error) {
    box.textContent = 'Chapter access could not be checked. The payment prompt will open when strengthening is requested.';
  }
}

byId('loadProjectBtn').addEventListener('click', () => loadProject(byId('projectId').value.trim()));
byId('useSavedDraftBtn').addEventListener('click', () => {
  const draft = currentProject?.drafts?.[String(chapterNumber())] || '';
  if (!draft.trim()) {
    uploadStatus.textContent = 'No saved draft was found for the selected chapter.';
    return;
  }
  chapterText.value = draft;
  uploadStatus.textContent = 'The saved project chapter draft has been loaded for strengthening.';
});

byId('recoverProjectsBtn').addEventListener('click', async () => {
  const resultsBox = byId('recoveryResults');
  resultsBox.textContent = 'Checking recovery details…';
  try {
    const response = await fetch('/api/projects/recover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: byId('recoverEmail').value.trim(),
        recovery_pin: byId('recoverPin').value.trim(),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'No project was recovered.');
    for (const credential of data.restored_access || []) {
      window.ProjectReadyPayments?.saveCredential?.(
        credential.project_id,
        credential.chapter_number,
        credential,
      );
    }
    resultsBox.innerHTML = '';
    data.projects.forEach((project) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'recovered-project';
      button.textContent = `${project.title} · ${project.academic_level || 'Level not set'} · ${project.id}`;
      button.addEventListener('click', () => loadProject(project.id));
      resultsBox.appendChild(button);
    });
  } catch (error) {
    resultsBox.textContent = error.message || 'Project recovery failed.';
  }
});

prefillStrengthenerRecoveryEmails();


function strengthenerJobStorageKey(project = projectId(), chapter = chapterNumber()) {
  return `projectready-strengthener-job:${project || 'unknown'}:chapter-${chapter || 0}`;
}

function renderStrengthenerJob(job = null) {
  const panel = byId('strengthenerJobPanel');
  if (!panel) return;
  panel.hidden = !job;
  if (!job) return;
  const progress = Math.max(0, Math.min(Number(job.progress || 0), 100));
  byId('strengthenerJobProgress').value = progress;
  byId('strengthenerJobPercent').textContent = `${progress}%`;
  byId('strengthenerJobStage').textContent = String(job.stage || job.status || 'Queued').replaceAll('_', ' ');
  byId('strengthenerJobMessage').textContent = job.message || 'Your chapter-strengthening request is being processed in the background.';
  byId('cancelStrengthenerJobBtn').hidden = !['queued', 'retrying'].includes(job.status);
}

function rememberStrengthenerJob(data) {
  activeStrengthenerJob = data;
  if (data?.job?.id && data?.job_token) {
    localStorage.setItem(strengthenerJobStorageKey(data.job.project_id, data.job.chapter_number), JSON.stringify(data));
  }
}

function forgetStrengthenerJob(data = activeStrengthenerJob) {
  if (data?.job?.project_id) {
    localStorage.removeItem(strengthenerJobStorageKey(data.job.project_id, data.job.chapter_number));
  }
  activeStrengthenerJob = null;
  renderStrengthenerJob(null);
}

async function readStrengthenerJob(data) {
  const response = await fetch(`/api/jobs/${encodeURIComponent(data.job.id)}`, {
    headers: { 'X-ProjectReady-Job-Token': data.job_token },
    cache: 'no-store',
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'The background strengthening request could not be checked.');
  return body.job;
}

async function pollStrengthenerJob(data) {
  rememberStrengthenerJob(data);
  let delay = 1500;
  while (true) {
    const job = await readStrengthenerJob(data);
    data.job = job;
    rememberStrengthenerJob(data);
    renderStrengthenerJob(job);
    message(job.message || `Background request: ${job.status}.`);
    if (job.status === 'completed') {
      forgetStrengthenerJob(data);
      return job.result || {};
    }
    if (job.status === 'failed') {
      forgetStrengthenerJob(data);
      throw new Error(job.error || 'The background strengthening request could not be completed. Your paid revision entitlement was returned where applicable.');
    }
    if (job.status === 'cancelled') {
      forgetStrengthenerJob(data);
      throw new Error('The queued strengthening request was cancelled.');
    }
    await new Promise((resolve) => window.setTimeout(resolve, delay));
    delay = Math.min(5000, Math.round(delay * 1.25));
  }
}

function applyStrengthenerResult(data) {
  lastResult = data;
  revisedChapter.value = data.revised_chapter_text || '';
  strengtheningReport.value = data.strengthening_report || '';
  supervisorMatrix.value = data.supervisor_response_matrix || '';
  supervisorMatrixPanel.hidden = !supervisorMatrix.value.trim();
  copyMatrixBtn.disabled = supervisorMatrixPanel.hidden;

  const sourceCount = Number(data.source_bank_count || 0);
  const scopeText = data.strengthening_scope === 'selected_sections' ? 'Selected-section output' : 'Complete selected chapter';
  const isolatedText = data.scope_metadata?.chapter_isolated
    ? ` A complete thesis was uploaded and Chapter ${data.scope_metadata.selected_chapter_number} was isolated before strengthening.`
    : '';
  revisionMeta.innerHTML = `<strong>${data.mode === 'ai_revision' ? 'Revision completed' : 'Fallback output returned'}.</strong> ${scopeText}. ${sourceCount} scholarly record(s) passed to the revision workflow. Estimated length: ${Number(data.estimated_pages || 0).toLocaleString()} pages and ${Number(data.word_count || 0).toLocaleString()} words. Citation density: ${Number(data.citations_per_1000_words || 0).toLocaleString()} per 1,000 words. Target: ${data.target_page_range || ''} pages and ${data.target_citation_density || ''}.${isolatedText} ${data.revision_colour_note || ''}`;

  enableOutputs(Boolean(revisedChapter.value.trim()));
  const errors = Array.isArray(data.provider_errors) ? data.provider_errors.filter(Boolean) : [];
  const saveMessage = data.saved_as_section_output
    ? ' The selected-section output was saved in the Chapter Strengthener record without replacing the complete project chapter.'
    : (data.saved_to_project ? ' The strengthened chapter was saved to the project.' : '');
  message(errors.length
    ? `Revision completed with ${errors.length} provider warning(s). Review the report and action items.`
    : `Working revision completed.${saveMessage} Review the working revision, report, sources, facts and all action items before export or academic use.`);
  updateAccessSummary();
}

async function resumeStrengthenerJobIfAvailable() {
  if (!projectId() || strengthenerJobInFlight) return;
  const prefix = `projectready-strengthener-job:${projectId()}:`;
  const key = Object.keys(localStorage).find((item) => item.startsWith(prefix));
  if (!key) return;
  let data = null;
  try {
    data = JSON.parse(localStorage.getItem(key) || 'null');
  } catch (_error) {
    localStorage.removeItem(key);
    return;
  }
  if (!data?.job?.id || !data?.job_token) return;
  strengthenerJobInFlight = true;
  setBusy(true);
  enableOutputs(false);
  try {
    const result = await pollStrengthenerJob(data);
    applyStrengthenerResult(result);
  } catch (error) {
    message(error.message || 'The background strengthening request could not be resumed.', 'error');
  } finally {
    strengthenerJobInFlight = false;
    setBusy(false);
  }
}

async function cancelActiveStrengthenerJob() {
  const data = activeStrengthenerJob;
  if (!data?.job?.id || !data?.job_token) return;
  const response = await fetch(`/api/jobs/${encodeURIComponent(data.job.id)}/cancel`, {
    method: 'POST',
    headers: { 'X-ProjectReady-Job-Token': data.job_token },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'The queued strengthening request could not be cancelled.');
  forgetStrengthenerJob(data);
  message(body.job?.message || 'The queued strengthening request was cancelled.');
  setBusy(false);
  strengthenerJobInFlight = false;
}

byId('cancelStrengthenerJobBtn')?.addEventListener('click', async () => {
  try {
    await cancelActiveStrengthenerJob();
  } catch (error) {
    message(error.message || 'The queued request could not be cancelled.', 'error');
  }
});

function enableOutputs(enabled) {
  copyChapterBtn.disabled = !enabled;
  copyReportBtn.disabled = !enabled;
  downloadRevisionBtn.disabled = !enabled;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (strengthenerJobInFlight) return;
  const payload = payloadFromForm();
  if (!payload.academic_integrity_confirmed || !payload.user_contribution_confirmed) {
    message('Confirm both academic-integrity and user-contribution declarations before strengthening the chapter.', 'error');
    return;
  }
  if (!payload.thesis_title || payload.chapter_text.length < 100) {
    message('Provide the thesis title and paste or upload the existing chapter.', 'error');
    return;
  }
  if (payload.chapter_type.startsWith('4.') && !payload.data_and_results.trim()) {
    message('Chapter Four strengthening requires confirmed results or findings. Paste the available results before continuing.', 'error');
    return;
  }
  if (payload.strengthening_scope === 'selected_sections' && !(payload.selected_section_titles.length || payload.new_section_titles.length || payload.custom_new_sections.length)) {
    message('Select at least one section to strengthen or add before using selected-sections mode.', 'error');
    return;
  }
  if (payload.custom_target_pages_enabled && (!payload.target_page_min || !payload.target_page_max || payload.target_page_max < payload.target_page_min)) {
    message('Enter a valid custom page range. The maximum must be equal to or greater than the minimum.', 'error');
    return;
  }

  strengthenerJobInFlight = true;
  setBusy(true);
  enableOutputs(false);
  copyMatrixBtn.disabled = true;
  message('Preparing the chapter-strengthening request…');

  try {
    await Promise.resolve(window.ProjectReadySessionBootstrap?.ready);
    if (selectedSourceMode() === 'external' && (!projectId() || currentProject?.profile?.project_kind !== 'external_revision')) {
      message('Creating the recoverable revision-only project…');
      await createExternalRevisionProject(payload);
    }
    if (!projectId()) throw new Error('Connect, recover or create a project before strengthening this chapter.');

    message('Queueing the chapter-strengthening request. You may leave this page after it enters the background queue.');
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/chapter-strengthener/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': requestId(),
        ...paymentHeaders(),
      },
      body: JSON.stringify(payload),
    });
    const queued = await response.json().catch(() => ({}));
    if (!response.ok) await handleProtectedError(response, queued, 'Chapter strengthening could not be queued.');
    rememberStrengthenerJob(queued);
    renderStrengthenerJob(queued.job);
    const result = await pollStrengthenerJob(queued);
    applyStrengthenerResult(result);
  } catch (error) {
    message(error.message || 'Chapter strengthening failed.', 'error');
  } finally {
    strengthenerJobInFlight = false;
    setBusy(false);
  }
});

async function initialiseStrengthener() {
  const params = new URLSearchParams(window.location.search);
  const explicitNewJob = params.get(STRENGTHENER_NEW_JOB_PARAM) === '1';
  if (explicitNewJob) clearStrengthenerStoredJobState();
  try {
    await Promise.resolve(window.ProjectReadySessionBootstrap?.ready);
  } catch (_error) {
    // Public users continue without a authorised session.
  }
  if (explicitNewJob) {
    resetStrengthenerForNewJob();
    history.replaceState({}, document.title, strengthenerPagePath());
    return;
  }
  await loadProject();
  await resumeStrengthenerJobIfAvailable();
}

window.addEventListener('projectready:session-ready', () => {
  updateAccessSummary().catch(() => {});
});

initialiseStrengthener().catch((error) => message(error.message || 'The Chapter Strengthener could not be initialised.', 'error'));

async function copyText(value, successMessage) {
  if (!value.trim()) return;
  try {
    await navigator.clipboard.writeText(value);
    message(successMessage);
  } catch (_error) {
    message('Copying was blocked by the browser. Select the text and copy it manually.', 'error');
  }
}

copyChapterBtn.addEventListener('click', () => copyText(revisedChapter.value, 'Strengthened chapter copied.'));
copyReportBtn.addEventListener('click', () => copyText(strengtheningReport.value, 'Strengthening report copied.'));
copyMatrixBtn.addEventListener('click', () => copyText(supervisorMatrix.value, 'Supervisor response matrix copied.'));

downloadRevisionBtn.addEventListener('click', async () => {
  if (!lastResult || !revisedChapter.value.trim()) return;
  message('Preparing the DOCX with revisions in blue and action items in red…');
  downloadRevisionBtn.disabled = true;

  try {
    if (!projectId()) throw new Error('Connect a project before exporting.');
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/chapter-strengthener/export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': requestId(),
        ...paymentHeaders(),
      },
      body: JSON.stringify({
        chapter_title: byId('chapterTitle').value.trim() || byId('chapterType').value,
        chapter_type: byId('chapterType').value,
        academic_level: byId('academicLevel').value,
        original_chapter_text: lastResult?.processed_original_chapter_text || chapterText.value.trim(),
        revised_chapter_text: revisedChapter.value,
        strengthening_report: strengtheningReport.value,
        supervisor_response_matrix: supervisorMatrix.value,
        include_strengthening_report: true,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      await handleProtectedError(response, data, 'Chapter export failed.');
    }

    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : 'projectready_strengthened_working_revision.docx';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    message('Working revision DOCX exported. Revisions are blue, action items are red and unchanged wording remains black. Verify and revise it before any submission.');
    updateAccessSummary();
  } catch (error) {
    message(error.message || 'Chapter export failed.', 'error');
  } finally {
    downloadRevisionBtn.disabled = false;
  }
});

byId('clearBtn').addEventListener('click', () => {
  clearStrengthenerAndStartNewJob().catch((error) => {
    message(error.message || 'The current strengthening job could not be cleared.', 'error');
  });
});
