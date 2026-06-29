const byId = (id) => document.getElementById(id);

const form = byId('revisionForm');
const chapterText = byId('chapterText');
const supervisorComments = byId('supervisorComments');
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
let currentProject = null;

let lastResult = null;

function message(text, kind = '') {
  statusBox.textContent = text || '';
  statusBox.className = `status ${kind}`.trim();
}

function setBusy(busy) {
  reviseBtn.disabled = busy;
  reviseBtn.textContent = busy ? 'Strengthening chapter…' : 'Strengthen chapter';
}

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

async function updateTargetNote() {
  try {
    const response = await fetch('/api/chapter-strengthener/targets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        academic_level: byId('academicLevel').value,
        chapter_type: byId('chapterType').value,
      }),
    });
    const data = await response.json();
    if (!response.ok) return;
    targetNote.textContent = `Planning target: ${data.page_range.minimum}-${data.page_range.maximum} pages, approximately ${Number(data.word_range_estimate.minimum).toLocaleString()}-${Number(data.word_range_estimate.maximum).toLocaleString()} words, and ${data.citation_density_per_1000_words.minimum}-${data.citation_density_per_1000_words.maximum} citation occurrences per 1,000 words.`;
  } catch (_error) {
    targetNote.textContent = 'Planning target unavailable.';
  }
}

byId('academicLevel').addEventListener('change', updateTargetNote);
byId('chapterType').addEventListener('change', updateTargetNote);
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
    citation_style: byId('citationStyle').value,
    revision_level: byId('revisionLevel').value,
    revision_goals: byId('revisionGoals').value.trim(),
    supervisor_comments: supervisorComments.value.trim(),
    strengthen_structure: byId('strengthenStructure').checked,
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
  return byId('projectId').value.trim();
}

function paymentHeaders() {
  if (!window.ProjectReadyPayments || !projectId()) return {};
  return ProjectReadyPayments.paymentHeaders(projectId(), chapterNumber());
}

function accessOptions() {
  return {
    projectId: projectId(),
    chapterNumber: chapterNumber(),
    chapterTitle: byId('chapterTitle').value.trim() || byId('chapterType').value,
    academicLevel: byId('academicLevel').value,
    returnPath: '/chapter-strengthener',
  };
}

async function handleProtectedError(response, data, fallbackMessage) {
  const detail = data?.detail;
  const errorMessage = typeof detail === 'string' ? detail : (detail?.message || fallbackMessage);
  if ([401, 402].includes(Number(response.status)) && window.ProjectReadyPayments && projectId()) {
    message(errorMessage, 'error');
    try {
      await ProjectReadyPayments.openAccessGate(accessOptions(), detail || {message: errorMessage});
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
  if (value && typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}: ${item}`).join('\n');
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
  byId('sourceSearchTerms').value = profile.source_search_terms || byId('sourceSearchTerms').value;
  localStorage.setItem(PROJECT_STORAGE_KEY, project.id);
  byId('projectConnectionStatus').textContent = `Connected to ${project.title || 'ProjectReady AI project'} (${project.id}). Project details and attached source records have been loaded.`;
  byId('useSavedDraftBtn').disabled = false;
  updateTargetNote();
  updateAccessSummary();
}

async function loadProject(explicitId = '') {
  const id = explicitId || projectId() || new URLSearchParams(window.location.search).get('project_id') || localStorage.getItem(PROJECT_STORAGE_KEY) || '';
  if (!id) {
    byId('projectConnectionStatus').textContent = 'No current project was found. Create or open a project in the Thesis Workspace, then return here.';
    return;
  }
  byId('projectConnectionStatus').textContent = 'Loading project…';
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(id)}`, {cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Project could not be loaded.');
    fillFromProject(data);
  } catch (error) {
    currentProject = null;
    byId('projectConnectionStatus').textContent = error.message || 'Project could not be loaded.';
  }
}

async function updateAccessSummary() {
  const box = byId('chapterAccessSummary');
  if (!projectId()) {
    box.textContent = 'Connect a project before strengthening. A paid chapter includes one strengthening revision and one DOCX export.';
    return;
  }
  const credential = window.ProjectReadyPayments?.getCredential(projectId(), chapterNumber());
  if (!credential) {
    box.innerHTML = 'This chapter has not been unlocked in this browser. <button type="button" id="unlockStrengthenerChapter">Unlock chapter</button>';
    byId('unlockStrengthenerChapter')?.addEventListener('click', () => ProjectReadyPayments.openAccessGate(accessOptions(), {message: 'Chapter strengthening uses the revision included with a paid chapter.'}));
    return;
  }
  try {
    const entitlement = await ProjectReadyPayments.checkEntitlement(projectId(), chapterNumber());
    const remaining = entitlement.remaining || {};
    if (entitlement.allowed) {
      box.textContent = `Payment confirmed. Remaining revision: ${remaining.revision ?? 0}. Remaining export: ${remaining.export ?? 0}.`;
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
byId('chapterType').addEventListener('change', updateAccessSummary);
byId('academicLevel').addEventListener('change', updateAccessSummary);
loadProject();

function enableOutputs(enabled) {
  copyChapterBtn.disabled = !enabled;
  copyReportBtn.disabled = !enabled;
  downloadRevisionBtn.disabled = !enabled;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = payloadFromForm();
  if (!payload.thesis_title || payload.chapter_text.length < 100) {
    message('Provide the thesis title and paste or upload the existing chapter.', 'error');
    return;
  }
  if (payload.chapter_type.startsWith('4.') && !payload.data_and_results.trim()) {
    message('Chapter Four strengthening requires confirmed results or findings. Paste the available results before continuing.', 'error');
    return;
  }

  setBusy(true);
  enableOutputs(false);
  copyMatrixBtn.disabled = true;
  message('Strengthening the chapter and checking academic alignment…');

  try {
    if (!projectId()) throw new Error('Connect a ProjectReady AI project before strengthening this chapter.');
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId())}/chapter-strengthener/revise`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': requestId(),
        ...paymentHeaders(),
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) await handleProtectedError(response, data, 'Chapter strengthening failed.');

    lastResult = data;
    revisedChapter.value = data.revised_chapter_text || '';
    strengtheningReport.value = data.strengthening_report || '';
    supervisorMatrix.value = data.supervisor_response_matrix || '';
    supervisorMatrixPanel.hidden = !supervisorMatrix.value.trim();
    copyMatrixBtn.disabled = supervisorMatrixPanel.hidden;

    const sourceCount = Number(data.source_bank_count || 0);
    revisionMeta.innerHTML = `<strong>${data.mode === 'ai_revision' ? 'Revision completed' : 'Fallback output returned'}.</strong> ${sourceCount} scholarly record(s) passed to the revision workflow. Estimated length: ${Number(data.estimated_pages || 0).toLocaleString()} pages and ${Number(data.word_count || 0).toLocaleString()} words. Citation density: ${Number(data.citations_per_1000_words || 0).toLocaleString()} per 1,000 words. Target: ${data.target_page_range || ''} pages and ${data.target_citation_density || ''}. ${data.revision_colour_note || ''}`;

    enableOutputs(Boolean(revisedChapter.value.trim()));
    const errors = Array.isArray(data.provider_errors) ? data.provider_errors.filter(Boolean) : [];
    message(errors.length ? `Revision completed with ${errors.length} provider warning(s). Review the report and action items.` : `Revision completed.${data.saved_to_project ? ' The strengthened chapter was saved to the project.' : ''} Review the chapter, report and all action items before downloading.`);
    updateAccessSummary();
  } catch (error) {
    message(error.message || 'Chapter strengthening failed.', 'error');
  } finally {
    setBusy(false);
  }
});

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
    if (!projectId()) throw new Error('Connect a ProjectReady AI project before exporting.');
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
        original_chapter_text: chapterText.value.trim(),
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
    const filename = match ? match[1] : 'projectready_strengthened_chapter_blue.docx';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    message('DOCX downloaded. Revisions are blue, action items are red and unchanged wording remains black.');
    updateAccessSummary();
  } catch (error) {
    message(error.message || 'Chapter export failed.', 'error');
  } finally {
    downloadRevisionBtn.disabled = false;
  }
});

byId('clearBtn').addEventListener('click', () => {
  form.reset();
  chapterText.value = '';
  supervisorComments.value = '';
  revisedChapter.value = '';
  strengtheningReport.value = '';
  supervisorMatrix.value = '';
  supervisorMatrixPanel.hidden = true;
  lastResult = null;
  revisionMeta.textContent = 'Revision details will appear here.';
  uploadStatus.textContent = '';
  message('');
  enableOutputs(false);
  copyMatrixBtn.disabled = true;
  updateTargetNote();
});
