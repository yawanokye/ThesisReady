const $ = (id) => document.getElementById(id);
let lastIdeaText = "";
let lastIdeaResult = null;
const TOPIC_ACCESS_STORAGE_KEY = "projectready-topic-ideas-access-v1";
const TOPIC_FORM_STORAGE_KEY = "projectready-topic-ideas-form-v1";
const FREE_PREVIEW_IDEAS = 2;
const PAID_MAXIMUM_IDEAS = 12;
let paidAccessReady = false;
let runtimeTopicCredential = null;
let topicAccessPlan = null;
let activeGenerationController = null;
let activeGenerationSequence = 0;

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
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const raw = await response.text();
  let data = {};
  try { data = raw ? JSON.parse(raw) : {}; } catch (_) { data = { detail: raw }; }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : (data.detail?.message || data.message || response.statusText);
    const error = new Error(detail || "Request failed.");
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function readTopicCredential() {
  if (runtimeTopicCredential?.purchase_id && runtimeTopicCredential?.access_token) {
    return runtimeTopicCredential;
  }
  for (const storage of [sessionStorage, localStorage]) {
    try {
      const value = JSON.parse(storage.getItem(TOPIC_ACCESS_STORAGE_KEY) || "null");
      if (value?.purchase_id && value?.access_token) {
        runtimeTopicCredential = value;
        return value;
      }
    } catch (_) {}
  }
  return null;
}

function saveTopicCredential(data) {
  if (!data?.purchase_id || !data?.access_token) {
    throw new Error("The server did not return a complete Topic Ideas access credential.");
  }
  const credential = {
    purchase_id: data.purchase_id,
    access_token: data.access_token,
    access_id: data.access_id || data.project_id || "",
    provider: data.provider || "",
    saved_at: new Date().toISOString(),
  };
  runtimeTopicCredential = credential;
  for (const storage of [sessionStorage, localStorage]) {
    try { storage.setItem(TOPIC_ACCESS_STORAGE_KEY, JSON.stringify(credential)); } catch (_) {}
  }
  const recoveryInput = $("topicRecoveryPurchaseId");
  if (recoveryInput) recoveryInput.value = credential.purchase_id;
  return credential;
}

function clearTopicCredential() {
  runtimeTopicCredential = null;
  for (const storage of [sessionStorage, localStorage]) {
    try { storage.removeItem(TOPIC_ACCESS_STORAGE_KEY); } catch (_) {}
  }
}

function topicAccessHeaders() {
  const credential = readTopicCredential();
  if (!credential) return {};
  return {
    "X-ProjectReady-Purchase-ID": credential.purchase_id,
    "X-ProjectReady-Access-Token": credential.access_token,
    "X-Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
  };
}

function registrationProfile() {
  for (const key of ["projectready-registration", "projectready-user-profile", "projectready_profile"]) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || "null");
      if (value?.email) return value;
    } catch (_) {}
  }
  return null;
}

function selectedTopicMarket() {
  return document.querySelector('input[name="topicMarket"]:checked')?.value || "ghana";
}

function ghanaTopicPriceDisplay(plan = null) {
  const display = String(plan?.ghana?.display || "").trim();
  if (/^GHS\s*10(?:\.00)?$/i.test(display)) return "GHS 10";
  return display && /^GHS/i.test(display) ? display : "GHS 10";
}

function internationalTopicPriceDisplay(plan = null) {
  const display = String(plan?.international?.display || "").trim();
  return display && /^US\$/i.test(display) ? display : "US$1.50";
}

function updateGenerationControls(unlocked) {
  paidAccessReady = Boolean(unlocked);
  const select = $("maxIdeas");
  const button = $("generateIdeasBtn");
  const help = $("maxIdeasHelp");
  if (select) select.disabled = !paidAccessReady;
  if (button) button.textContent = paidAccessReady ? "Generate unlocked ideas" : "Generate 2 free ideas";
  if (help) {
    help.textContent = paidAccessReady
      ? "Choose 5, 8, 10 or 12 ideas for your one unlocked generation."
      : "Your free preview returns 2 ideas. Unlock to choose up to 12.";
  }
}

function setTopicAccessState(kind, message) {
  const badge = $("topicAccessBadge");
  const status = $("topicAccessStatus");
  badge.className = `topic-access-badge ${kind || ""}`.trim();
  badge.textContent = kind === "ready"
    ? "Up to 12 unlocked"
    : kind === "used"
      ? "Unlock used"
      : "2 ideas free";
  status.textContent = message;
}

async function checkTopicAccess({ quiet = false, allowRecovery = true } = {}) {
  const credential = readTopicCredential();
  if (!credential) {
    updateGenerationControls(false);
    setTopicAccessState("free", "Generate your first 2 ideas free. Unlock only when you want a fuller set of up to 12 ideas.");
    return false;
  }
  try {
    const result = await api("/api/topic-ideas/payment-status", {
      method: "POST",
      body: JSON.stringify({ purchase_id: credential.purchase_id, access_token: credential.access_token }),
    });
    const remaining = Number(result.remaining?.draft || 0);
    if (result.allowed && remaining > 0) {
      updateGenerationControls(true);
      const select = $("maxIdeas");
      if (select && Number(select.value || 0) < 5) select.value = "12";
      setTopicAccessState("ready", `Payment confirmed. Choose 5, 8, 10 or 12 ideas for the unlocked generation before ${String(result.expires_at || "").slice(0, 10)}.`);
      return true;
    }
    updateGenerationControls(false);
    if (String(result.status || "").toLowerCase() === "pending") {
      setTopicAccessState("free", result.verification_message
        ? `Payment is not yet confirmed: ${result.verification_message}`
        : "Payment is still being confirmed. Select Check access again in a few seconds.");
      return false;
    }
    setTopicAccessState("used", remaining < 1
      ? "The unlocked generation has been used. You may still generate a new 2-idea free preview or purchase another unlock."
      : "This access is no longer active. The 2-idea free preview remains available.");
    return false;
  } catch (error) {
    const email = $("topicPaymentEmail")?.value.trim() || "";
    if (allowRecovery && error.status === 403 && credential.purchase_id && email) {
      try {
        await recoverTopicAccess(credential.purchase_id, email, { quiet: true });
        return checkTopicAccess({ quiet, allowRecovery: false });
      } catch (_) {
        // Fall through to the clear user-facing message below.
      }
    }
    updateGenerationControls(false);
    if (!quiet) {
      setTopicAccessState("free", `${error.message || "Paid access could not be verified."} Use Restore paid access below if payment was completed.`);
    }
    return false;
  }
}

async function loadTopicAccessPlan() {
  try {
    const plan = await api("/api/topic-ideas/access-plan");
    topicAccessPlan = plan;
    const environment = plan.payment_environment || {};
    if ($("topicGhanaPrice")) {
      $("topicGhanaPrice").textContent = `${ghanaTopicPriceDisplay(plan)} through ${plan.ghana?.provider || "Paystack"}`;
    }
    if ($("topicInternationalPrice")) {
      $("topicInternationalPrice").textContent = `${internationalTopicPriceDisplay(plan)} through Stripe`;
    }
    if ($("topicMarketNote")) {
      $("topicMarketNote").textContent = "Choose Ghana only when Ghana is your billing country. International payments are processed in US dollars.";
    }
    return plan;
  } catch (_) {
    topicAccessPlan = null;
    return null;
  }
}

async function redeemTopicHandoff(handoff) {
  const data = await api("/api/topic-ideas/redeem-handoff", {
    method: "POST",
    body: JSON.stringify({ handoff }),
  });
  saveTopicCredential(data);
  return data;
}

async function recoverTopicAccess(purchaseId, email, { quiet = false } = {}) {
  const cleanPurchaseId = String(purchaseId || "").trim();
  const cleanEmail = String(email || "").trim();
  if (!cleanPurchaseId) throw new Error("Enter the Purchase ID shown after payment.");
  if (!cleanEmail || !cleanEmail.includes("@")) throw new Error("Enter the same email address used for payment.");
  if (!quiet) $("topicAccessStatus").textContent = "Verifying the paid transaction and restoring access...";
  const data = await api("/api/topic-ideas/recover-access", {
    method: "POST",
    body: JSON.stringify({ purchase_id: cleanPurchaseId, email: cleanEmail }),
  });
  saveTopicCredential(data);
  if (!quiet) setTopicAccessState("ready", "Paid access restored. Choose 5, 8, 10 or 12 ideas.");
  return data;
}

async function restoreTopicAccessFromForm() {
  const button = $("restoreTopicAccessBtn");
  const purchaseId = $("topicRecoveryPurchaseId")?.value.trim() || readTopicCredential()?.purchase_id || "";
  const email = $("topicPaymentEmail")?.value.trim() || "";
  button.disabled = true;
  try {
    await recoverTopicAccess(purchaseId, email);
    const ready = await checkTopicAccess({ allowRecovery: false });
    if (ready) {
      $("ideaStatus").textContent = "Access restored. Choose how many ideas you want, then select Generate unlocked ideas.";
    }
  } catch (error) {
    updateGenerationControls(false);
    setTopicAccessState("free", error.message || "Paid access could not be restored.");
  } finally {
    button.disabled = false;
  }
}

async function startTopicIdeasCheckout() {
  const button = $("unlockTopicIdeasBtn");
  const email = $("topicPaymentEmail").value.trim();
  if (!email || !email.includes("@")) {
    setTopicAccessState("", "Enter a valid payment email address.");
    $("topicPaymentEmail").focus();
    return;
  }
  saveTopicFormDraftForCheckout();
  button.disabled = true;
  $("topicAccessStatus").textContent = "Creating secure checkout to unlock up to 12 ideas...";
  try {
    const data = await api("/api/topic-ideas/checkout", {
      method: "POST",
      body: JSON.stringify({
        email,
        market: selectedTopicMarket(),
        return_path: "/topic-ideas",
      }),
    });
    saveTopicCredential(data);
    if (!data.checkout_url) throw new Error("The payment provider did not return a checkout URL.");
    window.location.assign(data.checkout_url);
  } catch (error) {
    setTopicAccessState("", error.message || "Checkout could not start.");
    button.disabled = false;
  }
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

function clearTopicFormDraft() {
  for (const storage of [sessionStorage, localStorage]) {
    try { storage.removeItem(TOPIC_FORM_STORAGE_KEY); } catch (_) {}
  }
}

function saveTopicFormDraftForCheckout() {
  const payload = {
    version: 2,
    reason: "payment_checkout",
    saved_at: new Date().toISOString(),
    expires_at: Date.now() + (2 * 60 * 60 * 1000),
    form: collectPayload(),
  };
  for (const storage of [sessionStorage, localStorage]) {
    try { storage.setItem(TOPIC_FORM_STORAGE_KEY, JSON.stringify(payload)); } catch (_) {}
  }
}

function restoreTopicFormDraft({ paymentReturn = false } = {}) {
  if (!paymentReturn) {
    clearTopicFormDraft();
    return false;
  }
  try {
    let stored = null;
    for (const storage of [sessionStorage, localStorage]) {
      try {
        stored = JSON.parse(storage.getItem(TOPIC_FORM_STORAGE_KEY) || "null");
        if (stored) break;
      } catch (_) {}
    }
    if (!stored) return false;
    const value = stored.form || stored;
    if (stored.expires_at && Number(stored.expires_at) < Date.now()) {
      clearTopicFormDraft();
      return false;
    }
    const mappings = {
      researchArea: "research_area",
      context: "context",
      countryRegion: "country_region",
      level: "level",
      methodology: "methodology",
      dataType: "data_type",
      keywords: "keywords",
      trendFocus: "trend_focus",
      maxIdeas: "max_ideas",
    };
    Object.entries(mappings).forEach(([id, key]) => {
      if ($(id) && value[key] !== undefined && value[key] !== null) $(id).value = String(value[key]);
    });
    if ($("includeOlderFoundational") && value.include_older_foundational !== undefined) {
      $("includeOlderFoundational").checked = Boolean(value.include_older_foundational);
    }
    clearTopicFormDraft();
    return true;
  } catch (_) {
    clearTopicFormDraft();
    return false;
  }
}

function resetIdeaOutputs(message = "Your current job is clear. Enter a new research area to begin.") {
  $("ideaMeta").innerHTML = "";
  $("ideaResults").className = "idea-results empty-state";
  $("ideaResults").innerHTML = `<p>${escapeHtml(message)}</p>`;
  $("sourceRecords").innerHTML = "";
  lastIdeaText = "";
  lastIdeaResult = null;
  $("copyIdeasBtn").disabled = true;
  if ($("exportIdeasBtn")) $("exportIdeasBtn").disabled = true;
  showFreePreviewUnlock(false);
}

function resetTopicFormForNewJob({ preservePayment = true } = {}) {
  const paymentEmail = preservePayment ? ($("topicPaymentEmail")?.value || "") : "";
  const market = preservePayment ? selectedTopicMarket() : "ghana";
  $("ideaForm").reset();
  if ($("topicPaymentEmail")) $("topicPaymentEmail").value = paymentEmail;
  const marketRadio = document.querySelector(`input[name="topicMarket"][value="${market}"]`);
  if (marketRadio) marketRadio.checked = true;
  if ($("researchArea")) $("researchArea").value = "";
  if ($("context")) $("context").value = "";
  if ($("countryRegion")) $("countryRegion").value = "";
  if ($("keywords")) $("keywords").value = "";
  if ($("trendFocus")) $("trendFocus").value = "";
  if ($("topicRecoveryPurchaseId")) $("topicRecoveryPurchaseId").value = readTopicCredential()?.purchase_id || "";
}

function showFreePreviewUnlock(show = true) {
  const panel = $("freePreviewUnlock");
  if (!panel) return;
  panel.hidden = !show;
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
      ${renderMatchedBadges(source.matched_topic_terms || [])}
      ${source.topic_match_reason ? `<p class="resource-topic-match">${escapeHtml(source.topic_match_reason)}</p>` : ""}
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
      ${renderMatchedBadges(source.matched_topic_terms || [])}
      ${source.topic_match_reason ? `<p class="resource-topic-match">${escapeHtml(source.topic_match_reason)}</p>` : ""}
      ${source.access_and_adaptation_note ? `<p class="resource-caution">${escapeHtml(source.access_and_adaptation_note)}</p>` : ""}
      ${resourceLink(source.url || (source.doi ? `https://doi.org/${source.doi}` : ""), "Open publication record")}
    </article>`;
  }).join("")}</div>`;
}

function renderResearchResources(idea) {
  const guidance = idea.research_resource_guidance || {};
  const secondary = guidance.show_secondary_data === false
    ? []
    : normaliseList(guidance.secondary_data_sources);
  const instruments = guidance.show_instruments === false
    ? []
    : normaliseList(guidance.questionnaire_or_instrument_sources);
  if (!secondary.length && !instruments.length) return "";
  const basis = normaliseList(guidance.search_basis);
  const topicScope = guidance.topic_scope || idea.title || "this proposed topic";
  return `
    <section class="idea-box resource-guidance-box">
      <div class="resource-guidance-head">
        <div>
          <strong>Verified topic-specific research resources</strong>
          <p>Search scope: ${escapeHtml(topicScope)}. Weak or general matches are not displayed.</p>
        </div>
      </div>
      ${basis.length ? `<div class="idea-badge-row resource-basis">${basis.map(item => `<span class="badge">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      ${secondary.length ? `<div class="resource-group"><h4>Strongly matched secondary-data candidates</h4>${renderSecondarySources(secondary)}</div>` : ""}
      ${instruments.length ? `<div class="resource-group"><h4>Strongly matched questionnaire, scale, interview-guide or instrument candidates</h4>${renderInstrumentSources(instruments)}</div>` : ""}
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
  lastIdeaResult = result;
  const meta = $("ideaMeta");
  const ideasBox = $("ideaResults");
  const sourceBox = $("sourceRecords");
  const excluded = result.excluded_retracted_count || 0;
  const accessLabel = result.free_preview
    ? `Free preview: ${Number(result.ideas_returned || 2)} of up to ${Number(result.paid_maximum_ideas || PAID_MAXIMUM_IDEAS)} ideas`
    : `Unlocked set: ${Number(result.ideas_returned || (result.ideas || []).length)} ideas`;
  meta.innerHTML = `
    <strong>Access:</strong> ${escapeHtml(accessLabel)}<br />
    <strong>Academic level:</strong> ${escapeHtml(result.selected_level || "Not specified")}<br />
    <strong>Trend summary:</strong> ${escapeHtml(result.trend_summary || "No trend summary returned.")}<br />
    <strong>Search query:</strong> ${escapeHtml(result.query || "")}<br />
    <strong>Recent-reference window:</strong> ${escapeHtml(result.recent_reference_window || "")}<br />
    <strong>Trend databases:</strong> ${escapeHtml((result.databases || []).join(", "))}<br />
    <strong>Literature records used for trend grounding:</strong> ${Number(result.trend_source_records_used || (result.source_records_used || []).length || 0)}${result.trend_source_records_available ? ` of ${Number(result.trend_source_records_available)} relevant records retrieved` : ""}<br />
    <strong>Resource-search databases:</strong> ${escapeHtml(((result.resource_search || {}).databases || []).join(", ") || "No additional database reached")}<br />
    <strong>Detected retracted/withdrawn records excluded:</strong> ${excluded}
  `;

  const ideas = result.ideas || [];
  if (!ideas.length) {
    ideasBox.className = "idea-results empty-state";
    ideasBox.innerHTML = "<p>No ideas were returned. Refine the research area and try again.</p>";
    $("copyIdeasBtn").disabled = true;
    if ($("exportIdeasBtn")) $("exportIdeasBtn").disabled = true;
    lastIdeaResult = null;
    showFreePreviewUnlock(false);
    return;
  }

  showFreePreviewUnlock(Boolean(result.free_preview));
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
        ${normaliseList(idea.possible_data_sources).length ? `<div class="idea-box"><strong>Topic-specific data direction</strong><div class="idea-badge-row">${listText(idea.possible_data_sources || [])}</div></div>` : ""}
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
Topic-specific data direction: ${dataSources}
${secondarySources !== "   None returned" ? `Strongly matched secondary data sources:
${secondarySources}
` : ""}${instrumentSources !== "   None returned" ? `Strongly matched questionnaire or instrument sources:
${instrumentSources}
` : ""}Contribution: ${idea.potential_contribution || ""}
Attention note: ${idea.attention_note || ""}
`;
  }).join("\n");
  $("copyIdeasBtn").disabled = false;
  if ($("exportIdeasBtn")) $("exportIdeasBtn").disabled = false;
}

async function exportIdeasDocx() {
  if (!lastIdeaResult?.ideas?.length) return;
  const button = $("exportIdeasBtn");
  button.disabled = true;
  const previousLabel = button.textContent;
  button.textContent = "Preparing DOCX...";
  $("ideaStatus").textContent = "Preparing an editable DOCX file of the topic ideas...";
  try {
    const response = await fetch("/api/topic-ideas/export-docx", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result: lastIdeaResult }),
    });
    if (!response.ok) {
      const raw = await response.text();
      let message = raw || "DOCX export failed.";
      try {
        const data = JSON.parse(raw);
        message = typeof data.detail === "string" ? data.detail : (data.detail?.message || message);
      } catch (_) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
    const filename = filenameMatch ? decodeURIComponent(filenameMatch[1].replaceAll('"', "")) : "projectready_topic_ideas.docx";
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    $("ideaStatus").textContent = "Topic ideas exported to an editable DOCX file.";
  } catch (error) {
    $("ideaStatus").textContent = `DOCX export error: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = previousLabel;
  }
}

async function generateIdeas(event) {
  event.preventDefault();
  const payload = collectPayload();
  if (!payload.research_area) {
    $("ideaStatus").textContent = "Please enter a research area or broad topic.";
    return;
  }

  const accessReady = await checkTopicAccess({ quiet: true });
  payload.max_ideas = accessReady
    ? Math.max(5, Math.min(Number(payload.max_ideas || PAID_MAXIMUM_IDEAS), PAID_MAXIMUM_IDEAS))
    : FREE_PREVIEW_IDEAS;

  if (activeGenerationController) activeGenerationController.abort();
  activeGenerationController = new AbortController();
  const generationSequence = ++activeGenerationSequence;
  resetIdeaOutputs("Generating the current job. Previous results have been removed.");
  $("ideaStatus").textContent = accessReady
    ? `Searching current literature and generating ${payload.max_ideas} unlocked topic ideas...`
    : "Searching current literature and generating your 2 free topic ideas...";
  $("generateIdeasBtn").disabled = true;
  showFreePreviewUnlock(false);
  clearTopicFormDraft();

  try {
    const result = await api("/api/topic-ideas", {
      method: "POST",
      headers: accessReady ? topicAccessHeaders() : {},
      body: JSON.stringify(payload),
      signal: activeGenerationController.signal,
    });
    if (generationSequence !== activeGenerationSequence) return;
    renderIdeas(result);
    const providerErrors = (result.provider_errors || []).length;
    if (result.free_preview) {
      $("ideaStatus").textContent = providerErrors
        ? `Your 2 free ideas are ready. ${providerErrors} metadata provider(s) could not be reached. Unlock to compare up to 12 ideas.`
        : "Your 2 free ideas are ready. Unlock to generate a fuller set of up to 12 ideas to compare and select from.";
      setTopicAccessState("free", "Free preview completed. Unlock up to 12 ideas for GHS 10 in Ghana or US$1.50 outside Ghana.");
    } else {
      $("ideaStatus").textContent = providerErrors
        ? `Generated the unlocked idea set. ${providerErrors} metadata provider(s) could not be reached.`
        : "Generated the unlocked topic ideas with idea-specific data sources and instruments. General resources were excluded.";
      await checkTopicAccess({ quiet: true });
    }
  } catch (err) {
    if (err.name === "AbortError" || generationSequence !== activeGenerationSequence) return;
    $("ideaStatus").textContent = `Error: ${err.message}`;
    if (err.status === 402) {
      updateGenerationControls(false);
      setTopicAccessState("free", `${err.message} You can still generate 2 ideas free.`);
    }
  } finally {
    if (generationSequence === activeGenerationSequence) {
      $("generateIdeasBtn").disabled = false;
      activeGenerationController = null;
    }
  }
}

function clearIdeas() {
  if (activeGenerationController) activeGenerationController.abort();
  activeGenerationController = null;
  activeGenerationSequence += 1;
  clearTopicFormDraft();
  resetTopicFormForNewJob({ preservePayment: true });
  resetIdeaOutputs();
  $("ideaStatus").textContent = "Old entries and results were cleared. Paid access and payment email were retained.";
  updateGenerationControls(paidAccessReady);
  window.setTimeout(() => $("researchArea")?.focus(), 0);
}

async function copyIdeas() {
  if (!lastIdeaText) return;
  await navigator.clipboard.writeText(lastIdeaText);
  $("ideaStatus").textContent = "Copied title ideas to clipboard.";
}

window.addEventListener("DOMContentLoaded", async () => {
  $("ideaForm").addEventListener("submit", generateIdeas);
  $("clearIdeasBtn").addEventListener("click", clearIdeas);
  $("copyIdeasBtn").addEventListener("click", copyIdeas);
  $("exportIdeasBtn")?.addEventListener("click", exportIdeasDocx);
  $("unlockTopicIdeasBtn").addEventListener("click", startTopicIdeasCheckout);
  $("unlockFromPreviewBtn").addEventListener("click", startTopicIdeasCheckout);
  $("checkTopicAccessBtn").addEventListener("click", () => checkTopicAccess());
  $("restoreTopicAccessBtn").addEventListener("click", restoreTopicAccessFromForm);
  try {
    await Promise.resolve(window.ProjectReadySessionBootstrap?.ready);
  } catch (_error) {
    // Public users continue without a authorised session.
  }
  const params = new URLSearchParams(window.location.search);
  const isPaymentReturn = ["success", "cancelled", "failed"].includes(params.get("payment") || "");
  resetTopicFormForNewJob({ preservePayment: false });
  restoreTopicFormDraft({ paymentReturn: isPaymentReturn });
  resetIdeaOutputs("Your current job is empty. Enter a research area to begin.");
  await loadTopicAccessPlan();
  updateGenerationControls(false);
  const profile = registrationProfile();
  if (profile?.email && !$("topicPaymentEmail").value) $("topicPaymentEmail").value = profile.email;

  const returnedPurchaseId = params.get("purchase_id") || "";
  const existingCredential = readTopicCredential();
  if ($("topicRecoveryPurchaseId")) {
    $("topicRecoveryPurchaseId").value = returnedPurchaseId || existingCredential?.purchase_id || "";
  }

  if (params.get("payment") === "success") {
    $("topicAccessStatus").textContent = "Payment received. Activating your up-to-12-ideas access...";
    let handoffError = null;
    const handoff = params.get("handoff") || "";
    try {
      if (handoff) {
        await redeemTopicHandoff(handoff);
      } else if (returnedPurchaseId && $("topicPaymentEmail").value.trim()) {
        await recoverTopicAccess(returnedPurchaseId, $("topicPaymentEmail").value.trim(), { quiet: true });
      }
    } catch (error) {
      handoffError = error;
    }

    let ready = await checkTopicAccess({ quiet: true });
    if (!ready && returnedPurchaseId && $("topicPaymentEmail").value.trim()) {
      try {
        await recoverTopicAccess(returnedPurchaseId, $("topicPaymentEmail").value.trim(), { quiet: true });
        ready = await checkTopicAccess({ quiet: true, allowRecovery: false });
      } catch (error) {
        handoffError = handoffError || error;
      }
    }

    if (ready) {
      $("ideaStatus").textContent = "Access confirmed. Choose 5, 8, 10 or 12 ideas, then select Generate unlocked ideas.";
      $("generateIdeasBtn").scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      const message = handoffError?.message || "Payment was received, but automatic access restoration is incomplete. Enter the payment email and Purchase ID below, then select Restore paid access.";
      setTopicAccessState("free", message);
      $("topicRecoveryPanel").open = true;
    }
    history.replaceState({}, "", window.location.pathname);
  } else if (params.get("payment") === "cancelled" || params.get("payment") === "failed") {
    setTopicAccessState("free", "Payment was not completed. You can try again when ready.");
    history.replaceState({}, "", window.location.pathname);
  } else {
    await checkTopicAccess({ quiet: true });
  }
});
