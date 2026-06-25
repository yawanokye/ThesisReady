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


function normaliseList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  return value ? [value] : [];
}

function resourceLink(url, label = "Open source") {
  if (!url) return "";
  return `<a class="resource-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
}

function renderMatchedBadges(values) {
  const items = normaliseList(values);
  if (!items.length) return "";
  return `<div class="resource-match-row"><span>Relevant to:</span>${items.map(item => `<em>${escapeHtml(item)}</em>`).join("")}</div>`;
}

function renderSecondarySources(resources) {
  const sources = normaliseList(resources);
  if (!sources.length) return `<p class="hint">No specific secondary-data candidate was found. Refine the constructs, context or data direction and search again.</p>`;
  return `<div class="research-resource-list">${sources.map(source => `
    <article class="research-resource-card">
      <div class="resource-card-head">
        <strong>${escapeHtml(source.name || "Unnamed data source")}</strong>
        <span>${escapeHtml(source.source_type || source.discovery_database || "Candidate source")}</span>
      </div>
      <p class="resource-provider">${escapeHtml(source.provider || source.discovery_database || "")}${source.year ? ` · ${escapeHtml(source.year)}` : ""}</p>
      ${source.description ? `<p>${escapeHtml(source.description)}</p>` : ""}
      ${renderMatchedBadges(source.matched_variables_or_constructs || [])}
      ${source.access_note ? `<p class="resource-caution">${escapeHtml(source.access_note)}</p>` : ""}
      ${resourceLink(source.url, "Open data source")}
    </article>
  `).join("")}</div>`;
}

function renderInstrumentSources(resources) {
  const sources = normaliseList(resources);
  if (!sources.length) return `<p class="hint">No likely questionnaire, scale, protocol or instrument source was found. Refine the construct names and search again.</p>`;
  return `<div class="research-resource-list">${sources.map(source => {
    const authors = Array.isArray(source.authors) ? source.authors.join(", ") : (source.authors || "");
    return `
    <article class="research-resource-card instrument-card">
      <div class="resource-card-head">
        <strong>${escapeHtml(source.title || "Untitled source")}</strong>
        <span>${escapeHtml(source.database || source.record_type || "Scholarly record")}</span>
      </div>
      <p class="resource-provider">${escapeHtml(authors)}${source.year ? ` (${escapeHtml(source.year)})` : ""}${source.source ? ` · ${escapeHtml(source.source)}` : ""}</p>
      ${source.candidate_use ? `<p>${escapeHtml(source.candidate_use)}</p>` : ""}
      ${renderMatchedBadges(source.matched_constructs || [])}
      ${source.access_and_adaptation_note ? `<p class="resource-caution">${escapeHtml(source.access_and_adaptation_note)}</p>` : ""}
      ${resourceLink(source.url || (source.doi ? `https://doi.org/${source.doi}` : ""), "Open publication record")}
    </article>`;
  }).join("")}</div>`;
}

function renderResearchResources(idea) {
  const guidance = idea.research_resource_guidance || {};
  const secondary = normaliseList(guidance.secondary_data_sources);
  const instruments = normaliseList(guidance.questionnaire_or_instrument_sources);
  if (!secondary.length && !instruments.length) return "";
  const basis = normaliseList(guidance.search_basis);
  return `
    <section class="idea-box resource-guidance-box">
      <div class="resource-guidance-head">
        <div>
          <strong>Possible research data and instrument sources</strong>
          <p>Search matched to the variables and constructs proposed for this idea.</p>
        </div>
      </div>
      ${basis.length ? `<div class="idea-badge-row resource-basis">${basis.map(item => `<span class="badge">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      ${secondary.length ? `<div class="resource-group"><h4>Possible secondary data sources</h4>${renderSecondarySources(secondary)}</div>` : ""}
      ${instruments.length ? `<div class="resource-group"><h4>Possible questionnaire, scale, interview guide or instrument sources</h4>${renderInstrumentSources(instruments)}</div>` : ""}
      ${guidance.resource_note ? `<p class="resource-note">${escapeHtml(guidance.resource_note)}</p>` : ""}
    </section>
  `;
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
    <strong>Trend databases:</strong> ${escapeHtml((result.databases || []).join(", "))}<br />
    <strong>Resource-search databases:</strong> ${escapeHtml(((result.resource_search || {}).databases || []).join(", ") || "No additional database reached")}<br />
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
        <div class="idea-box"><strong>Likely data direction</strong><div class="idea-badge-row">${listText(idea.possible_data_sources || [])}</div></div>
      </div>
      ${renderResearchResources(idea)}
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
    const guidance = idea.research_resource_guidance || {};
    const secondarySources = normaliseList(guidance.secondary_data_sources).map((source, sourceIndex) =>
      `   ${sourceIndex + 1}. ${source.name || "Unnamed source"} | ${source.provider || source.discovery_database || ""} | ${(source.matched_variables_or_constructs || []).join(", ")} | ${source.url || ""}`
    ).join("\n") || "   None returned";
    const instrumentSources = normaliseList(guidance.questionnaire_or_instrument_sources).map((source, sourceIndex) =>
      `   ${sourceIndex + 1}. ${source.title || "Untitled source"} | ${(source.authors || []).join ? source.authors.join(", ") : (source.authors || "")} | ${source.year || ""} | ${(source.matched_constructs || []).join(", ")} | ${source.url || source.doi || ""}`
    ).join("\n") || "   None returned";

    return `${idx + 1}. ${idea.title}
Synopsis: ${idea.synopsis || ""}
General objective: ${objectives.general}
Specific objectives:
${specificText}
Level alignment: ${objectives.levelAlignment}
Trend/gap: ${idea.current_research_trend_or_gap || ""}
Method: ${idea.possible_methodology || ""}
Variables/constructs: ${variables}
Likely data direction: ${dataSources}
Possible secondary data sources:
${secondarySources}
Possible questionnaire or instrument sources:
${instrumentSources}
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
  $("ideaStatus").textContent = "Searching current literature, datasets and possible instrument sources, then generating title ideas...";
  $("generateIdeasBtn").disabled = true;
  try {
    const result = await api("/api/topic-ideas", { method: "POST", body: JSON.stringify(payload) });
    renderIdeas(result);
    const providerErrors = (result.provider_errors || []).length;
    $("ideaStatus").textContent = providerErrors
      ? `Generated ideas. ${providerErrors} metadata provider(s) could not be reached.`
      : "Generated title ideas, objectives, possible data sources and possible instrument sources.";
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
