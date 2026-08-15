(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const scriptUrl = new URL(document.currentScript?.src || window.location.href, window.location.origin);
  const portalBase = scriptUrl.pathname.replace(/\/portal\.js$/, "").replace(/\/$/, "");
  const endpoint = suffix => `${portalBase}/api/${String(suffix || "").replace(/^\//, "")}`;

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || "Request failed.");
    return data;
  }

  function showDashboard(active) {
    $("loginCard").hidden = active;
    $("dashboardCard").hidden = !active;
  }

  async function loadSession() {
    try {
      const data = await api(endpoint("session"));
      showDashboard(true);
      $("sessionStatus").textContent = `Restricted session active for ${data.email}.`;
      await Promise.all([loadJobs(), loadAccessPolicy(), loadComplimentaryTokens()]);
    } catch (_) {
      showDashboard(false);
    }
  }

  function actionButton(label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  async function loadJobs() {
    $("jobsStatus").textContent = "Loading background jobs…";
    try {
      const data = await api(endpoint("jobs?limit=60"));
      const body = $("jobsBody");
      body.innerHTML = "";
      for (const job of data.jobs || []) {
        const row = document.createElement("tr");
        const actions = document.createElement("td");
        actions.className = "job-actions";
        if (["queued", "retrying"].includes(job.status)) {
          actions.appendChild(actionButton("Cancel", async () => { await api(endpoint(`jobs/${job.id}/cancel`), {method:"POST"}); await loadJobs(); }));
        }
        if (["failed", "cancelled"].includes(job.status)) {
          actions.appendChild(actionButton("Retry", async () => { await api(endpoint(`jobs/${job.id}/retry`), {method:"POST"}); await loadJobs(); }));
        }
        row.innerHTML = `<td>${String(job.created_at || "").replace("T", " ").slice(0,19)}</td><td>${job.job_type || ""}</td><td>${(job.project_id || "").slice(0,12)} · Ch ${job.chapter_number || ""}</td><td>${job.status || ""}<br><small>${job.stage || ""}</small></td><td>${job.progress || 0}%</td>`;
        row.appendChild(actions);
        body.appendChild(row);
      }
      $("jobsStatus").textContent = `${(data.jobs || []).length} recent job(s).`;
    } catch (error) {
      $("jobsStatus").textContent = error.message;
    }
  }


  function formatExpiry(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  async function loadAccessPolicy() {
    const banner = $("currentAccessPolicy");
    try {
      const data = await api(endpoint("access-policy"));
      const policy = data.policy || {};
      const mode = policy.mode || "commercial";
      if ($("accessMode")) $("accessMode").value = mode;
      if ($("openHoursLabel")) $("openHoursLabel").hidden = mode !== "temporary_open";
      banner.className = `policy-banner ${mode === "temporary_open" ? "open" : mode === "payment_required" ? "locked" : ""}`;
      banner.textContent = mode === "temporary_open"
        ? `Temporary Open Access is active until ${formatExpiry(policy.open_until)}.`
        : mode === "payment_required"
          ? "Payment Required is active. Free Starter chapter generation is disabled."
          : "Normal commercial mode is active. Free Starter and paid chapter rules apply.";
      return policy;
    } catch (error) {
      banner.textContent = error.message;
      return null;
    }
  }

  async function applyAccessPolicy() {
    const mode = $("accessMode").value;
    $("accessPolicyStatus").textContent = "Applying access mode…";
    try {
      const payload = {mode};
      if (mode === "temporary_open") payload.open_hours = Number($("openHours").value || 12);
      const data = await api(endpoint("access-policy"), {method:"POST", body:JSON.stringify(payload)});
      $("accessPolicyStatus").textContent = "Access mode updated.";
      await loadAccessPolicy();
      return data;
    } catch (error) {
      $("accessPolicyStatus").textContent = error.message;
    }
  }

  function tokenActionButton(token) {
    if (["revoked", "expired"].includes(token.effective_status)) return document.createTextNode("—");
    return actionButton("Revoke", async () => {
      if (!window.confirm(`Revoke ${token.masked_id}?`)) return;
      await api(endpoint(`complimentary-tokens/${token.id}/revoke`), {method:"POST", body:"{}"});
      await loadComplimentaryTokens();
    });
  }

  async function loadComplimentaryTokens() {
    const body = $("complimentaryTokensBody");
    try {
      const data = await api(endpoint("complimentary-tokens?limit=100"));
      body.innerHTML = "";
      for (const token of data.tokens || []) {
        const row = document.createElement("tr");
        const action = document.createElement("td");
        action.appendChild(tokenActionButton(token));
        const state = token.effective_status || token.status || "unknown";
        row.innerHTML = `<td>${token.masked_id || ""}</td><td>${token.label || ""}${token.assigned_email ? `<br><small>${token.assigned_email}</small>` : ""}</td><td>${String(token.product_area || "all").replaceAll("_", " ")}</td><td>${token.pages_used || 0} / ${token.page_limit || 0}<br><small>${token.pages_remaining || 0} remaining</small></td><td>${formatExpiry(token.expires_at)}</td><td><span class="token-state ${state}">${state}</span></td>`;
        row.appendChild(action);
        body.appendChild(row);
      }
      $("complimentaryStatus").textContent = `${(data.tokens || []).length} complimentary token(s).`;
    } catch (error) {
      $("complimentaryStatus").textContent = error.message;
    }
  }

  async function createComplimentaryToken(event) {
    event.preventDefault();
    const reveal = $("newComplimentaryToken");
    reveal.hidden = true;
    $("complimentaryStatus").textContent = "Creating complimentary token…";
    try {
      const payload = {
        label: $("complimentaryLabel").value.trim(),
        assigned_email: $("complimentaryEmail").value.trim(),
        product_area: $("complimentaryProduct").value,
        page_limit: Number($("complimentaryPages").value || 0),
        validity_days: Number($("complimentaryDays").value || 30),
      };
      const data = await api(endpoint("complimentary-tokens"), {method:"POST", body:JSON.stringify(payload)});
      reveal.hidden = false;
      reveal.innerHTML = `<strong>Copy this token now. It cannot be shown again.</strong><span class="token-value" id="createdTokenValue"></span><div>${data.page_limit} page credits · ${String(data.product_area || "all").replaceAll("_", " ")} · expires ${formatExpiry(data.expires_at)}</div><button type="button" id="copyCreatedTokenBtn" class="secondary">Copy token</button>`;
      $("createdTokenValue").textContent = data.token || "";
      $("copyCreatedTokenBtn").addEventListener("click", async () => {
        await navigator.clipboard.writeText(data.token || "");
        $("copyCreatedTokenBtn").textContent = "Copied";
      });
      $("complimentaryStatus").textContent = data.message || "Complimentary token created.";
      await loadComplimentaryTokens();
    } catch (error) {
      $("complimentaryStatus").textContent = error.message;
    }
  }

  $("portalLoginForm").addEventListener("submit", async event => {
    event.preventDefault();
    $("loginStatus").textContent = "Checking restricted access…";
    try {
      await api(endpoint("session"), {method:"POST", body:JSON.stringify({email:$("portalEmail").value.trim(), key:$("portalKey").value.trim()})});
      $("portalKey").value = "";
      await loadSession();
    } catch (error) {
      $("loginStatus").textContent = error.message || "Access unavailable.";
    }
  });
  $("logoutBtn").addEventListener("click", async () => { await api(endpoint("session"), {method:"DELETE"}); showDashboard(false); });
  $("refreshJobsBtn").addEventListener("click", loadJobs);
  $("refreshAccessBtn").addEventListener("click", loadAccessPolicy);
  $("refreshTokensBtn").addEventListener("click", loadComplimentaryTokens);
  $("applyAccessPolicyBtn").addEventListener("click", applyAccessPolicy);
  $("accessMode").addEventListener("change", () => { $("openHoursLabel").hidden = $("accessMode").value !== "temporary_open"; });
  $("complimentaryTokenForm").addEventListener("submit", createComplimentaryToken);
  loadSession();
})();
