(() => {
  "use strict";
  const $ = id => document.getElementById(id);

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
      const data = await api("/api/internal/session");
      showDashboard(true);
      $("sessionStatus").textContent = `Restricted session active for ${data.email}.`;
      await loadJobs();
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
      const data = await api("/api/internal/jobs?limit=60");
      const body = $("jobsBody");
      body.innerHTML = "";
      for (const job of data.jobs || []) {
        const row = document.createElement("tr");
        const actions = document.createElement("td");
        actions.className = "job-actions";
        if (["queued", "retrying"].includes(job.status)) {
          actions.appendChild(actionButton("Cancel", async () => { await api(`/api/internal/jobs/${job.id}/cancel`, {method:"POST"}); await loadJobs(); }));
        }
        if (["failed", "cancelled"].includes(job.status)) {
          actions.appendChild(actionButton("Retry", async () => { await api(`/api/internal/jobs/${job.id}/retry`, {method:"POST"}); await loadJobs(); }));
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

  $("portalLoginForm").addEventListener("submit", async event => {
    event.preventDefault();
    $("loginStatus").textContent = "Checking restricted access…";
    try {
      await api("/api/internal/session", {method:"POST", body:JSON.stringify({email:$("portalEmail").value.trim(), key:$("portalKey").value.trim()})});
      $("portalKey").value = "";
      await loadSession();
    } catch (error) {
      $("loginStatus").textContent = error.message || "Access unavailable.";
    }
  });
  $("logoutBtn").addEventListener("click", async () => { await api("/api/internal/session", {method:"DELETE"}); showDashboard(false); });
  $("refreshJobsBtn").addEventListener("click", loadJobs);
  loadSession();
})();
