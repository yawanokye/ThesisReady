const $ = (id) => document.getElementById(id);
let lastIdeaText = "";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function collectPayload() {
  return {
    research_area: $("researchArea").value.trim(),
    context: $("context").value.trim(),
    country_region: $("countryRegion").value.trim(),
    level: $("level").value,
    methodology: $("methodology").value,
    data_type: $("dataType").value,
    keywords: $("keywords").value.trim(),
    trend_focus: $("trendFocus").value.trim(),
    max_ideas: Number($("maxIdeas").value || 8),
    include_older_foundational: $("includeOlderFoundational").checked,
  };
}

function listText(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map(x => `<span class="badge">${escapeHtml(x)}</span>`).join("");
  if (!value) return "";
  return `<span class="badge">${escapeHtml(value)}</span>`;
}


function normaliseObjectives(value) {
  if (!value || typeof value !== "object") {
    return { general: "", specific: [], levelAlignment: "" };
  }
  const specific = Array.isArray(value.specific_objectives)
    ? value.specific_objectives.filter(Boolean)
    : [];
  return {
    general: value.general_objective || "",
    specific,
    levelAlignment: value.level_alignment || "",
  };
}

function renderObjectives(idea) {
  const objectives = normaliseObjectives(idea.proposed_objectives);
  if (!objectives.general && !objectives.specific.length) return "";

  const specificList = objectives.specific.length
    ? `<ol class="objective-list">${objectives.specific.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`
    : `<p class="hint">No specific objectives were returned.</p>`;

  return `
    <div class="idea-box objective-box">
      <strong>Proposed research objectives</strong>
      ${objectives.general ? `<div class="objective-general"><span>General objective</span><p>${escapeHtml(objectives.general)}</p></div>` : ""}
      <div class="objective-specific"><span>Specific objectives</span>${specificList}</div>
      ${objectives.levelAlignment ? `<p class="objective-level-note">${escapeHtml(objectives.levelAlignment)}</p>` : ""}
    </div>
  `;
}

function renderIdeas(result) {
  const meta = $("ideaMeta");
  const ideasBox = $("ideaResults");
  const sourceBox = $("sourceRecords");
  const excluded = result.excluded_retracted_count || 0;
  meta.innerHTML = `
    <strong>Academic level:</strong> ${escapeHtml(result.selected_level || "Not specified")}<br />
    <strong>Trend summary:</strong> ${escapeHtml(result.trend_summary || "No trend summary returned.")}<br />
    <strong>Search query:</strong> ${escapeHtml(result.query || "")}<br />
    <strong>Recent-reference window:</strong> ${escapeHtml(result.recent_reference_window || "")}<br />
    <strong>Databases:</strong> ${escapeHtml((result.databases || []).join(", "))}<br />
    <strong>Detected retracted/withdrawn records excluded:</strong> ${excluded}
  `;

  const ideas = result.ideas || [];
  if (!ideas.length) {
    ideasBox.className = "idea-results empty-state";
    ideasBox.innerHTML = "<p>No ideas were returned. Refine the research area and try again.</p>";
    $("copyIdeasBtn").disabled = true;
    return;
  }

  ideasBox.className = "idea-results";
  ideasBox.innerHTML = ideas.map((idea, idx) => `
    <article class="idea-card">
      <h3>${idx + 1}. ${escapeHtml(idea.title || "Untitled idea")}</h3>
      <p>${escapeHtml(idea.synopsis || "")}</p>
      ${renderObjectives(idea)}
      <div class="idea-badge-row">${listText(idea.evidence_sources || [])}</div>
      <div class="idea-grid">
        <div class="idea-box"><strong>Current trend or gap</strong>${escapeHtml(idea.current_research_trend_or_gap || "")}</div>
        <div class="idea-box"><strong>Possible methodology</strong>${escapeHtml(idea.possible_methodology || "")}</div>
        <div class="idea-box"><strong>Variables or constructs</strong><div class="idea-badge-row">${listText(idea.possible_variables_or_constructs || [])}</div></div>
        <div class="idea-box"><strong>Possible data sources</strong><div class="idea-badge-row">${listText(idea.possible_data_sources || [])}</div></div>
      </div>
      <div class="idea-box"><strong>Potential contribution</strong>${escapeHtml(idea.potential_contribution || "")}</div>
      ${idea.attention_note ? `<div class="attention-note">${escapeHtml(idea.attention_note)}</div>` : ""}
    </article>
  `).join("");

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
  }).join("") : `<p class="hint">No source records were available for display.</p>`;

  lastIdeaText = ideas.map((idea, idx) => {
    const objectives = normaliseObjectives(idea.proposed_objectives);
    const specificText = objectives.specific.length
      ? objectives.specific.map((item, objectiveIndex) => `   ${objectiveIndex + 1}. ${item}`).join("\n")
      : "   None returned";
    const variables = Array.isArray(idea.possible_variables_or_constructs)
      ? idea.possible_variables_or_constructs.join(", ")
      : (idea.possible_variables_or_constructs || "");
    const dataSources = Array.isArray(idea.possible_data_sources)
      ? idea.possible_data_sources.join(", ")
      : (idea.possible_data_sources || "");

    return `${idx + 1}. ${idea.title}
Synopsis: ${idea.synopsis || ""}
General objective: ${objectives.general}
Specific objectives:
${specificText}
Level alignment: ${objectives.levelAlignment}
Trend/gap: ${idea.current_research_trend_or_gap || ""}
Method: ${idea.possible_methodology || ""}
Variables/constructs: ${variables}
Possible data sources: ${dataSources}
Contribution: ${idea.potential_contribution || ""}
Attention note: ${idea.attention_note || ""}
`;
  }).join("\n");
  $("copyIdeasBtn").disabled = false;
}

async function generateIdeas(event) {
  event.preventDefault();
  const payload = collectPayload();
  if (!payload.research_area) {
    $("ideaStatus").textContent = "Please enter a research area or broad topic.";
    return;
  }
  $("ideaStatus").textContent = "Searching current scholarly metadata and generating title ideas...";
  $("generateIdeasBtn").disabled = true;
  try {
    const result = await api("/api/topic-ideas", { method: "POST", body: JSON.stringify(payload) });
    renderIdeas(result);
    const providerErrors = (result.provider_errors || []).length;
    $("ideaStatus").textContent = providerErrors
      ? `Generated ideas. ${providerErrors} metadata provider(s) could not be reached.`
      : "Generated title ideas, brief synopses and level-appropriate objectives.";
  } catch (err) {
    $("ideaStatus").textContent = `Error: ${err.message}`;
  } finally {
    $("generateIdeasBtn").disabled = false;
  }
}

function clearIdeas() {
  $("ideaForm").reset();
  $("ideaMeta").innerHTML = "";
  $("ideaResults").className = "idea-results empty-state";
  $("ideaResults").innerHTML = "<p>Generated ideas will appear here.</p>";
  $("sourceRecords").innerHTML = "";
  $("ideaStatus").textContent = "";
  lastIdeaText = "";
  $("copyIdeasBtn").disabled = true;
}

async function copyIdeas() {
  if (!lastIdeaText) return;
  await navigator.clipboard.writeText(lastIdeaText);
  $("ideaStatus").textContent = "Copied title ideas to clipboard.";
}

window.addEventListener("DOMContentLoaded", () => {
  $("ideaForm").addEventListener("submit", generateIdeas);
  $("clearIdeasBtn").addEventListener("click", clearIdeas);
  $("copyIdeasBtn").addEventListener("click", copyIdeas);
});
