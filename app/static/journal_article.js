const $ = (id) => document.getElementById(id);
let lastArticleText = "";

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response;
}

function val(id) {
  return ($(id)?.value || "").trim();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[ch]));
}

function collectPayload() {
  return {
    article_title: val("articleTitle"),
    research_area: val("researchArea"),
    target_journal: val("targetJournal"),
    author_guidelines: val("authorGuidelines"),
    article_type: val("articleType"),
    academic_level: val("academicLevel"),
    methodology: val("methodology"),
    context: val("context"),
    research_problem: val("researchProblem"),
    objectives: val("objectives"),
    theory_or_framework: val("theoryFramework"),
    variables_constructs: val("variablesConstructs"),
    data_and_results: val("dataResults"),
    key_findings: val("keyFindings"),
    contribution: val("keyFindings"),
    references_notes: val("referencesNotes"),
    word_limit: val("wordLimit"),
    citation_style: val("citationStyle"),
    include_source_search: $("includeSourceSearch").checked,
    include_older_foundational: $("includeOlderFoundational").checked,
  };
}

function renderSources(result) {
  const filters = result.quality_filters || [];
  const excluded = result.excluded_retracted_count || 0;
  const filterBox = $("qualityFilters");
  filterBox.innerHTML = filters.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  if (excluded) {
    filterBox.insertAdjacentHTML("beforeend", `<div class="warning-note">${excluded} detected retracted/withdrawn source record(s) were excluded from drafting.</div>`);
  }

  const sourceBox = $("sourceRecords");
  const sources = result.source_records_used || [];
  sourceBox.innerHTML = sources.length ? sources.map(src => {
    const authors = Array.isArray(src.authors) ? src.authors.join(", ") : (src.authors || "");
    const link = src.url ? `<a href="${escapeHtml(src.url)}" target="_blank" rel="noopener">Open record</a>` : "";
    return `<div class="source-record">
      <strong>${escapeHtml(src.key || "S?")}: ${escapeHtml(src.title || "Untitled source")}</strong>
      <div class="sub">${escapeHtml(authors)} ${src.year ? "(" + escapeHtml(src.year) + ")" : ""}</div>
      <div class="sub">${escapeHtml(src.source || src.database || "")}</div>
      ${link}
    </div>`;
  }).join("") : `<p class="hint">No source records were available for display. Add verified references or enable source search.</p>`;
}

async function draftArticle(event) {
  event.preventDefault();
  const payload = collectPayload();
  if (!payload.article_title) {
    $("articleStatus").textContent = "Please enter a working article title or topic.";
    return;
  }
  $("articleStatus").textContent = "Searching sources and drafting the journal article...";
  $("draftArticleBtn").disabled = true;
  $("copyArticleBtn").disabled = true;
  $("downloadArticleBtn").disabled = true;
  try {
    const result = await api("/api/journal-article/draft", { method: "POST", body: JSON.stringify(payload) });
    lastArticleText = result.article_text || "";
    $("articleOutput").value = lastArticleText;
    renderSources(result);
    const errors = (result.provider_errors || []).length;
    $("articleStatus").textContent = errors
      ? `Draft completed with ${errors} provider warning(s). Review source records and placeholders.`
      : `Draft completed using ${result.model_used || "selected model"}.`;
    $("copyArticleBtn").disabled = !lastArticleText;
    $("downloadArticleBtn").disabled = !lastArticleText;
  } catch (err) {
    $("articleStatus").textContent = `Error: ${err.message}`;
  } finally {
    $("draftArticleBtn").disabled = false;
  }
}

function clearArticle() {
  $("articleForm").reset();
  $("wordLimit").value = "6000-8000";
  $("articleOutput").value = "";
  $("sourceRecords").innerHTML = "";
  $("qualityFilters").innerHTML = "";
  $("articleStatus").textContent = "";
  lastArticleText = "";
  $("copyArticleBtn").disabled = true;
  $("downloadArticleBtn").disabled = true;
}

async function copyArticle() {
  const text = $("articleOutput").value || lastArticleText;
  if (!text) return;
  await navigator.clipboard.writeText(text);
  $("articleStatus").textContent = "Copied article draft to clipboard.";
}

async function downloadArticle() {
  const text = $("articleOutput").value || lastArticleText;
  if (!text) return;
  $("articleStatus").textContent = "Preparing DOCX export...";
  try {
    const response = await fetch("/api/journal-article/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article_title: val("articleTitle") || "Journal Article Draft", article_text: text }),
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "journal_article_draft.docx";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    $("articleStatus").textContent = "DOCX downloaded.";
  } catch (err) {
    $("articleStatus").textContent = `Export error: ${err.message}`;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("articleForm").addEventListener("submit", draftArticle);
  $("clearArticleBtn").addEventListener("click", clearArticle);
  $("copyArticleBtn").addEventListener("click", copyArticle);
  $("downloadArticleBtn").addEventListener("click", downloadArticle);
});
