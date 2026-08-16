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


let strengthenerAccessState = null;
let strengthenerComplimentaryState = null;
let lastStrengthenerTarget = null;
let strengthenerSelectedPapers = [];

function setStrengthenerFlowStep(name, complete, current) {
  const node = document.querySelector(`#strengthenerFlowSteps [data-flow-step="${name}"]`);
  if (!node) return;
  node.classList.toggle('complete', Boolean(complete));
  node.classList.toggle('current', Boolean(current));
}

function strengthenerHasPaidCredential() {
  return Boolean(window.ProjectReadyPayments?.getCredential?.(projectId(), chapterNumber(), 'chapter_strengthener'));
}

function updateStrengthenerFlow() {
  const sourceMode = selectedSourceMode();
  const sourceReady = sourceMode === 'external' || Boolean(projectId());
  const chapterReady = Boolean(byId('thesisTitle')?.value.trim() && chapterText?.value.trim().length >= 100);
  const chapterNo = chapterNumber();
  const logicSignals = [byId('objectives')?.value, byId('researchQuestions')?.value, byId('methodology')?.value, byId('theoryFramework')?.value].filter(Boolean).join(' ').trim();
  const logicReady = chapterReady && logicSignals.length >= 20 && (chapterNo !== 4 || byId('dataResults')?.value.trim().length >= 20);
  const directionReady = logicReady && Boolean(byId('revisionLevel')?.value);
  const supportReady = directionReady; // optional by design
  const accessReady = Boolean(
    strengthenerAccessState?.temporary_open ||
    strengthenerComplimentaryState?.allowed ||
    strengthenerHasPaidCredential()
  );
  const reviewed = Boolean(revisedChapter?.value.trim());
  const states = [
    ['source', sourceReady], ['chapter', chapterReady], ['logic', logicReady], ['direction', directionReady],
    ['support', supportReady], ['access', accessReady], ['review', reviewed]
  ];
  const firstIncomplete = states.find(([_, complete]) => !complete)?.[0] || 'review';
  states.forEach(([name, complete]) => setStrengthenerFlowStep(name, complete, name === firstIncomplete));
  const count = states.filter(([_, complete]) => complete).length;
  const labels = {source:'Choose or connect the chapter source.',chapter:'Add the chapter text and scope.',logic:'Complete the research logic needed for this chapter.',direction:'Choose the strengthening direction.',support:'Add optional supervisor comments or source support if needed.',access:'Confirm strengthening access.',review:'Strengthen, review and export the working revision.'};
  if (byId('strengthenerFlowSummary')) byId('strengthenerFlowSummary').textContent = count === states.length ? 'Strengthening workflow complete.' : `${count} of ${states.length} steps complete. ${labels[firstIncomplete] || ''}`;
}

function renderStrengthenerAccessStatus() {
  const badge = byId('strengthenerAccessModeBadge');
  const text = byId('strengthenerAccessModeText');
  if (!badge || !text) return;
  badge.className = 'access-mode-badge';
  if (strengthenerComplimentaryState?.allowed) {
    badge.classList.add('complimentary');
    badge.textContent = 'Complimentary';
    text.textContent = `${strengthenerComplimentaryState.pages_remaining} of ${strengthenerComplimentaryState.page_limit} page credits remain. Strengthening reserves the selected maximum page target.`;
  } else if (strengthenerAccessState?.temporary_open) {
    badge.classList.add('open');
    badge.textContent = 'Open access';
    const expiry = strengthenerAccessState.open_until ? new Date(strengthenerAccessState.open_until).toLocaleString() : 'the developer closes it';
    text.textContent = `Temporary open access is active until ${expiry}. Strengthening payment is bypassed during this window.`;
  } else if (strengthenerAccessState?.payment_required) {
    badge.classList.add('locked');
    badge.textContent = 'Payment required';
    text.textContent = strengthenerHasPaidCredential() ? 'Paid strengthening access is stored on this device.' : 'Paid, authorised internal or complimentary access is required.';
  } else {
    badge.textContent = strengthenerHasPaidCredential() ? 'Paid' : 'Commercial';
    text.textContent = strengthenerHasPaidCredential() ? 'Paid strengthening access is stored on this device.' : 'Normal commercial access is active. Unlock the chapter or apply a complimentary token before strengthening.';
  }
  updateStrengthenerFlow();
}

async function refreshStrengthenerAccessStatus() {
  if (!window.ProjectReadyPayments) return;
  try { strengthenerAccessState = await ProjectReadyPayments.accessStatus('chapter_strengthener'); }
  catch (_) { strengthenerAccessState = {mode:'commercial'}; }
  const stored = ProjectReadyPayments.getComplimentaryCredential?.();
  if (byId('strengthenerComplimentaryToken') && stored?.token && !byId('strengthenerComplimentaryToken').value) byId('strengthenerComplimentaryToken').value = stored.token;
  if (byId('strengthenerComplimentaryEmail') && stored?.email && !byId('strengthenerComplimentaryEmail').value) byId('strengthenerComplimentaryEmail').value = stored.email;
  if (stored?.token) {
    try { strengthenerComplimentaryState = await ProjectReadyPayments.complimentaryStatus('chapter_strengthener'); }
    catch (_) { strengthenerComplimentaryState = null; }
  } else strengthenerComplimentaryState = null;
  const status = byId('strengthenerComplimentaryStatus');
  if (status) {
    if (strengthenerComplimentaryState?.allowed) status.textContent = `${strengthenerComplimentaryState.label || 'Complimentary access'}: ${strengthenerComplimentaryState.pages_remaining} page credit(s) remaining, expires ${new Date(strengthenerComplimentaryState.expires_at).toLocaleDateString()}. The maximum strengthening page target must fit within this balance.`;
    else if (stored?.token) status.textContent = strengthenerComplimentaryState?.detail || 'This saved complimentary token is not valid for Chapter Strengthener.';
    else status.textContent = '';
  }
  renderStrengthenerAccessStatus();
}

async function applyStrengthenerComplimentaryAccess() {
  const token = byId('strengthenerComplimentaryToken')?.value.trim() || '';
  const email = byId('strengthenerComplimentaryEmail')?.value.trim() || '';
  if (!token) {
    if (byId('strengthenerComplimentaryStatus')) byId('strengthenerComplimentaryStatus').textContent = 'Enter the complimentary token first.';
    return;
  }
  ProjectReadyPayments.saveComplimentaryCredential(token, email);
  await refreshStrengthenerAccessStatus();
  if (!strengthenerComplimentaryState?.allowed && byId('strengthenerComplimentaryDetails')) byId('strengthenerComplimentaryDetails').open = true;
}

async function clearStrengthenerComplimentaryAccess() {
  ProjectReadyPayments.clearComplimentaryCredential();
  strengthenerComplimentaryState = null;
  if (byId('strengthenerComplimentaryToken')) byId('strengthenerComplimentaryToken').value = '';
  if (byId('strengthenerComplimentaryEmail')) byId('strengthenerComplimentaryEmail').value = '';
  if (byId('strengthenerComplimentaryStatus')) byId('strengthenerComplimentaryStatus').textContent = 'Complimentary token cleared from this device.';
  await refreshStrengthenerAccessStatus();
}


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
  strengthenerSelectedPapers = [];
  if (byId('strengthenerSelectedPapersList')) byId('strengthenerSelectedPapersList').innerHTML = '';
  if (byId('strengthenerSelectedPapersStatus')) byId('strengthenerSelectedPapersStatus').textContent = '';
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
let currentStrengthenerClaimReview = null;

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
  updateStrengthenerFlow();
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
        discipline: byId('discipline')?.value.trim() || '',
        strengthening_scope: byId('strengtheningScope')?.value || 'whole_chapter',
        selected_section_count: strengthen.length + add.length + customNewSections.length,
        ...customTargetPayload(),
      }),
    });
    const data = await response.json();
    if (!response.ok) return;
    lastStrengthenerTarget = data;
    const scopeLabel = data.strengthening_scope === 'selected_sections' ? 'selected-section output' : 'complete selected chapter';
    targetNote.textContent = `Planning target for the ${scopeLabel}: ${data.page_range.minimum}-${data.page_range.maximum} pages, approximately ${Number(data.word_range_estimate.minimum).toLocaleString()}-${Number(data.word_range_estimate.maximum).toLocaleString()} words, and ${data.citation_density_per_1000_words.minimum}-${data.citation_density_per_1000_words.maximum} verified referenced works per 1,000 words.${data.custom_target_applied ? ' Custom page target applied.' : ''}`;
    if (!byId('customTargetPagesEnabled')?.checked) {
      if (byId('targetPageMin')) byId('targetPageMin').placeholder = String(data.page_range.minimum);
      if (byId('targetPageMax')) byId('targetPageMax').placeholder = String(data.page_range.maximum);
    }
    updateStrengthenerFlow();
  } catch (_error) {
    targetNote.textContent = 'Planning target unavailable.';
  }
}

byId('academicLevel').addEventListener('change', () => {
  updateTargetNote();
  updateAccessSummary();
});

byId('discipline').addEventListener('change', () => {
  updateTargetNote();
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


function strengthenerPaperAuthors(paper) {
  return Array.isArray(paper?.authors) ? paper.authors.join('; ') : String(paper?.authors || '');
}

function strengthenerPersistedPapers() {
  const papers = currentProject?.profile?.selected_papers;
  return Array.isArray(papers) ? papers : [];
}

function renderStrengthenerSelectedPapers() {
  const box = byId('strengthenerSelectedPapersList');
  const status = byId('strengthenerSelectedPapersStatus');
  if (!box) return;
  const persisted = strengthenerPersistedPapers();
  const persistedKeys = new Set(persisted.map((paper) => String(paper?.doi || paper?.id || paper?.filename || '').toLowerCase()));
  const pending = strengthenerSelectedPapers.filter((paper) => !persistedKeys.has(String(paper?.doi || paper?.id || paper?.filename || '').toLowerCase()));
  const all = [
    ...persisted.map((paper) => ({paper, persisted: true})),
    ...pending.map((paper) => ({paper, persisted: false})),
  ];
  if (!all.length) {
    box.innerHTML = '<p class="help">No selected papers are attached. Automatic scholarly search can still support the strengthening request.</p>';
    if (status) status.textContent = '';
    return;
  }
  const ready = all.filter(({paper}) => paper?.citation_eligible).length;
  if (status) status.textContent = `${all.length} of 50 selected papers available; ${ready} citation-ready.`;
  box.innerHTML = all.map(({paper, persisted}, index) => {
    const citationReady = Boolean(paper.citation_eligible);
    const authors = strengthenerPaperAuthors(paper);
    return `
      <article class="selected-paper-card" data-strengthener-paper-id="${String(paper.id || '').replace(/"/g, '&quot;')}">
        <div class="selected-paper-card-head">
          <div><span class="selected-paper-number">Paper ${index + 1}</span><strong>${escapeHtmlLocal(paper.title || paper.filename || 'Uploaded paper')}</strong><small>${escapeHtmlLocal(paper.filename || '')}</small></div>
          <span class="selected-paper-badge ${citationReady ? 'ready' : 'needs-confirmation'}">${citationReady ? 'Citation ready' : 'Confirm metadata'}</span>
        </div>
        <div class="selected-paper-meta"><span>${escapeHtmlLocal(authors || 'Author details not confirmed')}</span><span>${escapeHtmlLocal(paper.year || 'Year not confirmed')}</span></div>
        <p class="help">${escapeHtmlLocal(paper.provenance_note || '')}</p>
        ${persisted ? '<p class="help">Saved with this project. Manage or remove it from the Thesis Workspace source library if needed.</p>' : `
        <details class="selected-paper-metadata-editor">
          <summary>${citationReady ? 'Review citation details' : 'Confirm citation details before citing'}</summary>
          <div class="selected-paper-editor-grid">
            <label>Title<input data-strengthener-paper-field="title" value="${escapeHtmlLocal(paper.title || '')}"></label>
            <label>Authors, separate with semicolons<input data-strengthener-paper-field="authors" value="${escapeHtmlLocal(authors)}"></label>
            <label>Year<input data-strengthener-paper-field="year" value="${escapeHtmlLocal(paper.year || '')}" maxlength="5"></label>
            <label>Journal / source<input data-strengthener-paper-field="source" value="${escapeHtmlLocal(paper.source || '')}"></label>
            <label>DOI<input data-strengthener-paper-field="doi" value="${escapeHtmlLocal(paper.doi || '')}"></label>
            <label>Stable URL<input data-strengthener-paper-field="url" value="${escapeHtmlLocal(paper.url || '')}"></label>
          </div>
          <div class="actions compact-actions"><button type="button" class="secondary compact-upload" data-strengthener-paper-confirm="${String(paper.id || '').replace(/"/g, '&quot;')}">Confirm citation details</button><button type="button" class="secondary compact-upload" data-strengthener-paper-remove="${String(paper.id || '').replace(/"/g, '&quot;')}">Remove</button></div>
        </details>`}
      </article>`;
  }).join('');
  box.querySelectorAll('[data-strengthener-paper-confirm]').forEach((button) => button.addEventListener('click', () => confirmStrengthenerPaperMetadata(button.dataset.strengthenerPaperConfirm)));
  box.querySelectorAll('[data-strengthener-paper-remove]').forEach((button) => button.addEventListener('click', () => removeStrengthenerSelectedPaper(button.dataset.strengthenerPaperRemove)));
}

function escapeHtmlLocal(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
}

async function attachStrengthenerSelectedPapers() {
  const input = byId('strengthenerSelectedPaperFiles');
  const files = Array.from(input?.files || []);
  if (!files.length) {
    byId('strengthenerSelectedPapersStatus').textContent = 'Choose one or more papers first.';
    return;
  }
  const existingCount = strengthenerPersistedPapers().length + strengthenerSelectedPapers.length;
  if (existingCount + files.length > 50) {
    byId('strengthenerSelectedPapersStatus').textContent = `Up to 50 selected papers are allowed. ${existingCount} are already attached or pending.`;
    return;
  }
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  byId('strengthenerSelectedPapersStatus').textContent = `Extracting ${files.length} selected paper(s)…`;
  const response = await fetch('/api/chapter-strengthener/extract-selected-papers', {method:'POST', body: formData});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Selected papers could not be processed.');
  const currentKeys = new Set([
    ...strengthenerPersistedPapers(), ...strengthenerSelectedPapers,
  ].map((paper) => String(paper?.doi || paper?.filename || paper?.id || '').toLowerCase()));
  for (const paper of data.papers || []) {
    const key = String(paper?.doi || paper?.filename || paper?.id || '').toLowerCase();
    if (!key || currentKeys.has(key)) continue;
    currentKeys.add(key);
    strengthenerSelectedPapers.push(paper);
  }
  if (input) input.value = '';
  renderStrengthenerSelectedPapers();
  byId('strengthenerSelectedPapersStatus').textContent = `${strengthenerSelectedPapers.length} new paper(s) ready for this strengthening request. ${data.citation_ready || 0} were citation-ready automatically. Papers without confirmed metadata remain evidence-only.`;
  updateStrengthenerFlow();
}

function confirmStrengthenerPaperMetadata(paperId) {
  const card = document.querySelector(`.selected-paper-card[data-strengthener-paper-id="${String(paperId || '')}"]`);
  const paper = strengthenerSelectedPapers.find((item) => String(item.id || '') === String(paperId || ''));
  if (!card || !paper) return;
  const val = (name) => card.querySelector(`[data-strengthener-paper-field="${name}"]`)?.value.trim() || '';
  const authors = val('authors').split(/\s*;\s*|\n+/).map((item) => item.trim()).filter(Boolean);
  const year = val('year');
  if (!val('title') || !authors.length || !/^(?:19|20)\d{2}[a-z]?$/.test(year)) {
    byId('strengthenerSelectedPapersStatus').textContent = 'To make a paper citation-ready, confirm its title, at least one author and a four-digit publication year.';
    return;
  }
  Object.assign(paper, {
    title: val('title'), authors, year, source: val('source'), doi: val('doi'), url: val('url'),
    user_metadata_confirmed: true, citation_eligible: true, user_verified: true,
    metadata_status: paper.metadata_verified ? 'verified_crossref' : 'confirmed_by_user',
    provenance_note: paper.metadata_verified ? 'Full text was uploaded by the user and citation metadata was verified.' : 'Full text and citation details were uploaded/confirmed by the user.',
  });
  renderStrengthenerSelectedPapers();
  byId('strengthenerSelectedPapersStatus').textContent = 'Citation details confirmed for this paper. It may now be cited only where its uploaded evidence supports the claim.';
}

function removeStrengthenerSelectedPaper(paperId) {
  strengthenerSelectedPapers = strengthenerSelectedPapers.filter((item) => String(item.id || '') !== String(paperId || ''));
  renderStrengthenerSelectedPapers();
  byId('strengthenerSelectedPapersStatus').textContent = `${strengthenerSelectedPapers.length} new selected paper(s) remain for this request.`;
}

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
    selected_papers: strengthenerSelectedPapers,
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
  renderStrengthenerSelectedPapers();

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
  const savedReview = (profile.claim_support_reviews || {})[`strengthener:${chapterNumber()}`] || null;
  const savedStrengthener = (profile.chapter_strengthener || {})[String(chapterNumber())] || null;
  if (savedStrengthener?.revised_chapter_text) {
    revisedChapter.value = savedStrengthener.revised_chapter_text;
    currentStrengthenerClaimReview = savedReview || savedStrengthener.claim_support_review || null;
    renderStrengthenerClaimSupportReview(currentStrengthenerClaimReview);
  }
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
  strengthenerSelectedPapers = [];
  renderStrengthenerSelectedPapers();
  return data;
}

async function updateAccessSummary() {
  const box = byId('chapterAccessSummary');
  await Promise.resolve(window.ProjectReadySessionBootstrap?.ready).catch(() => null);
  await refreshStrengthenerAccessStatus().catch(() => {});
  if (strengthenerComplimentaryState?.allowed) {
    box.textContent = `Complimentary access is active with ${strengthenerComplimentaryState.pages_remaining} page credit(s) remaining. The selected maximum page target must fit within this balance.`;
    return;
  }
  if (strengthenerAccessState?.temporary_open) {
    box.textContent = 'Temporary open access is active. No strengthening payment will be required during the developer-defined access window.';
    return;
  }
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
    if (strengthenerAccessState?.payment_required) {
      box.textContent = 'Payment Required mode is active. Use paid access, authorised internal access or a valid complimentary token before strengthening.';
    }
    const label = isRevisionOnlyProject() ? 'Unlock revision-only access' : 'Unlock chapter';
    const explanation = strengthenerAccessState?.payment_required
      ? 'Payment Required mode is active. Use paid access, authorised internal access or a valid complimentary token before strengthening.'
      : (isRevisionOnlyProject()
        ? 'This external chapter uses a revision-only plan with one strengthening revision, one compliance check and one DOCX export.'
        : 'Chapter strengthening uses the revision included with a paid chapter.');
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
  currentStrengthenerClaimReview = data.claim_support_review || null;
  renderStrengthenerClaimSupportReview(currentStrengthenerClaimReview);
  strengtheningReport.value = data.strengthening_report || '';
  supervisorMatrix.value = data.supervisor_response_matrix || '';
  supervisorMatrixPanel.hidden = !supervisorMatrix.value.trim();
  copyMatrixBtn.disabled = supervisorMatrixPanel.hidden;

  const sourceCount = Number(data.source_bank_count || 0);
  const scopeText = data.strengthening_scope === 'selected_sections' ? 'Selected-section output' : 'Complete selected chapter';
  const isolatedText = data.scope_metadata?.chapter_isolated
    ? ` A complete thesis was uploaded and Chapter ${data.scope_metadata.selected_chapter_number} was isolated before strengthening.`
    : '';
  revisionMeta.innerHTML = `<strong>${data.mode === 'ai_revision' ? 'Revision completed' : 'Fallback output returned'}.</strong> ${scopeText}. ${sourceCount} scholarly record(s) passed to the revision workflow. Estimated length: ${Number(data.estimated_pages || 0).toLocaleString()} pages and ${Number(data.word_count || 0).toLocaleString()} words. Verified/user-supplied reference density: ${Number(data.references_per_1000_words ?? data.citations_per_1000_words ?? 0).toLocaleString()} per 1,000 words. Target: ${data.target_page_range || ''} pages and ${data.target_citation_density || ''}.${isolatedText} ${data.revision_colour_note || ''}`;

  enableOutputs(Boolean(revisedChapter.value.trim()));
  const errors = Array.isArray(data.provider_errors) ? data.provider_errors.filter(Boolean) : [];
  const saveMessage = data.saved_as_section_output
    ? ' The selected-section output was saved in the Chapter Strengthener record without replacing the complete project chapter.'
    : (data.saved_to_project ? ' The strengthened chapter was saved to the project.' : '');
  message(errors.length
    ? `Revision completed with ${errors.length} provider warning(s). Review the report and action items.`
    : `Working revision completed.${saveMessage} Review the working revision, report, sources, facts and all action items before export or academic use.`);
  updateAccessSummary();
  updateStrengthenerFlow();
}


function strengthenerClaimItems(review = currentStrengthenerClaimReview) {
  if (!review) return [];
  return [...(review.claims || []), ...(review.paragraph_density_gaps || [])];
}

function findStrengthenerClaimItem(itemId) {
  return strengthenerClaimItems().find(item => String(item.id || '') === String(itemId || ''));
}

function strengthenerCandidateAuthorText(candidate) {
  const authors = Array.isArray(candidate?.authors) ? candidate.authors : [candidate?.authors].filter(Boolean);
  return authors.slice(0,4).join(', ') || 'Author metadata unavailable';
}

function renderStrengthenerCandidates(item) {
  const candidates = Array.isArray(item.candidates) ? item.candidates : [];
  if (!candidates.length) return '';
  const approvedIds = new Set((item.approved_sources || []).map(source => source.candidate_id || source.doi || source.title));
  return `<div class="claim-support-candidates">${candidates.map(candidate => {
    const id = escapeHtmlLocal(candidate.candidate_id || '');
    const identity = candidate.candidate_id || candidate.doi || candidate.title;
    const approved = approvedIds.has(identity);
    const locator = candidate.doi ? `https://doi.org/${String(candidate.doi).replace('https://doi.org/','').replace('http://doi.org/','')}` : candidate.url;
    const link = locator ? `<a href="${escapeHtmlLocal(locator)}" target="_blank" rel="noopener">Open source</a>` : '';
    const evidence = candidate.evidence_excerpt ? `<p class="claim-source-evidence"><strong>Accessible evidence:</strong> ${escapeHtmlLocal(candidate.evidence_excerpt)}</p>` : `<p class="claim-source-evidence"><strong>Evidence text unavailable in the search record.</strong> Open the source and confirm it manually before approval.</p>`;
    const manual = candidate.requires_manual_source_text_confirmation ? `<label class="check claim-support-small"><input type="checkbox" data-strength-source-reviewed="${id}"> I opened the source text and confirmed it supports this claim.</label>` : '';
    return `<article class="claim-source-candidate ${approved ? 'claim-source-approved' : ''}">
      <strong>${escapeHtmlLocal(candidate.title || 'Untitled source')}</strong>
      <p class="claim-source-meta">${escapeHtmlLocal(strengthenerCandidateAuthorText(candidate))} (${escapeHtmlLocal(candidate.year || 'n.d.')}) · ${escapeHtmlLocal(candidate.journal || candidate.database || '')} ${link}</p>
      ${evidence}${manual}
      <button type="button" class="secondary" data-strength-approve-source="${escapeHtmlLocal(item.id)}" data-candidate-id="${id}" ${approved ? 'disabled' : ''}>${approved ? 'Approved' : 'Approve as support'}</button>
    </article>`;
  }).join('')}</div>`;
}

function renderStrengthenerHighlightedPreview() {
  const preview = byId('strengthenerHighlightedPreview');
  if (!preview) return;
  let safe = escapeHtmlLocal(revisedChapter?.value || '');
  for (const item of (currentStrengthenerClaimReview?.claims || [])) {
    if (item.status === 'resolved') continue;
    const target = escapeHtmlLocal(item.claim_text || '');
    if (target && safe.includes(target)) safe = safe.replace(target, `<span class="unsupported-claim-highlight" title="Claim needs verified source support">${target}</span>`);
  }
  preview.innerHTML = safe.replace(/(\[[^\]\n]{3,}\])/g, '<span class="placeholder-text">$1</span>');
}

function renderStrengthenerClaimSupportReview(review = currentStrengthenerClaimReview) {
  currentStrengthenerClaimReview = review || null;
  const panel = byId('strengthenerClaimSupportPanel');
  const list = byId('strengthenerClaimSupportList');
  const summary = byId('strengthenerClaimSupportSummary');
  const badge = byId('strengthenerClaimSupportBadge');
  if (!panel || !list || !summary || !badge) return;
  if (!review) { panel.hidden = true; renderStrengthenerHighlightedPreview(); enableOutputs(Boolean(revisedChapter.value.trim())); return; }
  panel.hidden = false;
  const ready = Boolean(review.final_output_ready);
  badge.textContent = ready ? 'Evidence gate passed' : 'Review required';
  badge.classList.toggle('ready', ready);
  summary.innerHTML = `<div><strong>${Number(review.unsupported_claim_count || 0)}</strong><br>claims without citations</div><div><strong>${Number(review.under_supported_paragraph_count || 0)}</strong><br>paragraphs below 2 verified sources</div><div><strong>${Number(review.paragraph_citation_audit?.minimum_coverage_percent ?? 0)}%</strong><br>paragraph minimum coverage</div>`;
  const items = strengthenerClaimItems(review);
  list.innerHTML = items.length ? items.map(item => {
    const isClaim = item.type === 'claim';
    const text = isClaim ? item.claim_text : item.excerpt;
    const approved = Array.isArray(item.approved_sources) ? item.approved_sources.length : 0;
    return `<article class="claim-support-card"><h4>${isClaim ? 'Claim needs source support' : `Paragraph needs ${item.minimum_verified_sources || 2}-${item.preferred_verified_sources || 3} distinct verified sources`}</h4>
      <p class="claim-support-small">${escapeHtmlLocal(item.heading || 'Chapter body')} · paragraph ${Number(item.paragraph_index || 0)}${isClaim ? `, sentence ${Number(item.sentence_index || 0)}` : ''} · ${approved} source(s) approved</p>
      <div class="claim-support-claim">${escapeHtmlLocal(text || '')}</div>
      <div class="actions"><button type="button" class="secondary" data-strength-find-sources="${escapeHtmlLocal(item.id)}">Find verified sources</button></div>
      ${renderStrengthenerCandidates(item)}</article>`;
  }).join('') : `<div class="claim-support-card"><strong>Claim-support review passed.</strong><p>No unsupported evidence-bearing claims or paragraph-density gaps remain.</p></div>`;
  list.querySelectorAll('[data-strength-find-sources]').forEach(button => button.addEventListener('click', () => findStrengthenerClaimSources(button.dataset.strengthFindSources).catch(error => { byId('strengthenerClaimSupportStatus').textContent = error.message || 'Source search failed.'; })));
  list.querySelectorAll('[data-strength-approve-source]').forEach(button => button.addEventListener('click', () => approveStrengthenerClaimSource(button.dataset.strengthApproveSource, button.dataset.candidateId).catch(error => { byId('strengthenerClaimSupportStatus').textContent = error.message || 'Source approval failed.'; })));
  renderStrengthenerHighlightedPreview();
  enableOutputs(Boolean(revisedChapter.value.trim()));
}

async function findStrengthenerClaimSources(itemId) {
  if (!projectId()) throw new Error('Connect or recover a project first.');
  const item = findStrengthenerClaimItem(itemId);
  if (!item) throw new Error('This claim is no longer present in the current review.');
  byId('strengthenerClaimSupportStatus').textContent = 'Searching verified scholarly sources for this claim…';
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/claim-support/find-sources`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({workflow:'strengthener', chapter_number:chapterNumber(), claim_id:itemId, query:item.search_query || item.claim_text || item.excerpt || '', max_results:12})
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Claim source search failed.');
  item.candidates = data.candidates || [];
  renderStrengthenerClaimSupportReview(currentStrengthenerClaimReview);
  byId('strengthenerClaimSupportStatus').textContent = `${item.candidates.length} candidate source(s) found. Review the evidence before approval.`;
}

async function approveStrengthenerClaimSource(itemId, candidateId) {
  const item = findStrengthenerClaimItem(itemId);
  const candidate = (item?.candidates || []).find(source => String(source.candidate_id || '') === String(candidateId || ''));
  if (!item || !candidate) throw new Error('Source candidate is no longer available.');
  const selector = `[data-strength-source-reviewed="${CSS.escape(String(candidateId))}"]`;
  const checked = candidate.requires_manual_source_text_confirmation ? Boolean(document.querySelector(selector)?.checked) : false;
  if (candidate.requires_manual_source_text_confirmation && !checked) throw new Error('Open the source and confirm that you checked its text before approval.');
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/claim-support/approve`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({workflow:'strengthener', chapter_number:chapterNumber(), claim_id:itemId, candidate_id:candidateId, confirm_claim_support:true, confirm_source_text_reviewed:checked})
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Source approval failed.');
  item.approved_sources = [...(item.approved_sources || []), {...candidate, candidate_id:candidate.candidate_id}].slice(0,3);
  renderStrengthenerClaimSupportReview(currentStrengthenerClaimReview);
  byId('strengthenerClaimSupportStatus').textContent = data.message || 'Source approved.';
}

async function applyStrengthenerApprovedSources() {
  if (!projectId()) throw new Error('Connect or recover a project first.');
  byId('strengthenerClaimSupportStatus').textContent = 'Applying only approved, verified citations and re-running the claim audit…';
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/claim-support/apply-approved`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({workflow:'strengthener', chapter_number:chapterNumber(), citation_style:byId('citationStyle')?.value || 'APA 7th'})
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Approved citations could not be applied.');
  revisedChapter.value = data.text || revisedChapter.value;
  if (lastResult) lastResult.revised_chapter_text = revisedChapter.value;
  currentStrengthenerClaimReview = data.review || null;
  renderStrengthenerClaimSupportReview(currentStrengthenerClaimReview);
  byId('strengthenerClaimSupportStatus').textContent = currentStrengthenerClaimReview?.final_output_ready ? 'All current claim-support and paragraph-density gaps are resolved. Export is unlocked.' : 'Approved citations were applied. Continue reviewing the remaining evidence gaps.';
}

async function refreshStrengthenerClaimReview() {
  if (!projectId()) return;
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/claim-support-review?workflow=strengthener&chapter_number=${chapterNumber()}`, {cache:'no-store'});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Claim-support review could not be refreshed.');
  currentStrengthenerClaimReview = data.review || null;
  renderStrengthenerClaimSupportReview(currentStrengthenerClaimReview);
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

byId('strengthenerApplyApprovedSourcesBtn')?.addEventListener('click', () => applyStrengthenerApprovedSources().catch(error => { byId('strengthenerClaimSupportStatus').textContent = error.message || 'Approved citations could not be applied.'; }));
byId('strengthenerRefreshClaimReviewBtn')?.addEventListener('click', () => refreshStrengthenerClaimReview().catch(error => { byId('strengthenerClaimSupportStatus').textContent = error.message || 'Claim-support review could not be refreshed.'; }));

byId('cancelStrengthenerJobBtn')?.addEventListener('click', async () => {
  try {
    await cancelActiveStrengthenerJob();
  } catch (error) {
    message(error.message || 'The queued request could not be cancelled.', 'error');
  }
});

function enableOutputs(enabled) {
  const evidenceReady = !currentStrengthenerClaimReview || Boolean(currentStrengthenerClaimReview.final_output_ready);
  copyChapterBtn.disabled = !enabled || !evidenceReady;
  copyReportBtn.disabled = !enabled;
  downloadRevisionBtn.disabled = !enabled || !evidenceReady;
  copyChapterBtn.classList.toggle('claim-review-locked', enabled && !evidenceReady);
  downloadRevisionBtn.classList.toggle('claim-review-locked', enabled && !evidenceReady);
  downloadRevisionBtn.title = enabled && !evidenceReady ? 'Complete the Claim Support Review before exporting the strengthened chapter.' : '';
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
  await refreshStrengthenerAccessStatus();
  updateStrengthenerFlow();
  await resumeStrengthenerJobIfAvailable();
}

window.addEventListener('projectready:session-ready', () => {
  updateAccessSummary().catch(() => {});
  refreshStrengthenerAccessStatus().catch(() => {});
});


byId('applyStrengthenerComplimentaryBtn')?.addEventListener('click', () => applyStrengthenerComplimentaryAccess().then(updateAccessSummary).catch((error) => { if (byId('strengthenerComplimentaryStatus')) byId('strengthenerComplimentaryStatus').textContent = error.message || 'Token could not be applied.'; }));
byId('clearStrengthenerComplimentaryBtn')?.addEventListener('click', () => clearStrengthenerComplimentaryAccess().then(updateAccessSummary).catch(() => {}));
byId('extractSelectedPapersBtn')?.addEventListener('click', () => attachStrengthenerSelectedPapers().catch((error) => { if (byId('strengthenerSelectedPapersStatus')) byId('strengthenerSelectedPapersStatus').textContent = error.message || 'Selected papers could not be attached.'; }));
document.addEventListener('input', (event) => { if (event.target?.closest?.('.strengthener-guided-frame')) updateStrengthenerFlow(); });
document.addEventListener('change', (event) => { if (event.target?.closest?.('.strengthener-guided-frame')) { updateStrengthenerFlow(); refreshStrengthenerAccessStatus().catch(() => {}); } });

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
