(() => {
  "use strict";
  const scriptUrl = new URL(document.currentScript?.src || window.location.href, window.location.origin);
  const portalBase = scriptUrl.pathname.replace(/\/module-session\.js$/, "").replace(/\/$/, "");

  async function activate() {
    const response = await fetch(`${portalBase}/api/module-access`, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: "{}",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.purchase_id || !data.access_token) {
      throw new Error(data.detail || "Authorised session is unavailable.");
    }
    const credential = {
      purchase_id: data.purchase_id,
      access_token: data.access_token,
      provider: data.provider || "authorised_session",
      product_area: "all",
      saved_at: new Date().toISOString(),
    };
    const prefix = "projectready-entitlement:";
    for (const chapter of [0, 1, 2, 3, 4, 5, 6, 7, 99]) {
      localStorage.setItem(`${prefix}internal:all:chapter-${chapter}`, JSON.stringify(credential));
    }
    localStorage.setItem(`${prefix}purchase:${data.purchase_id}`, JSON.stringify(credential));
    const topic = {...credential, access_id: "authorised-session"};
    sessionStorage.setItem("projectready-topic-ideas-access-v1", JSON.stringify(topic));
    localStorage.setItem("projectready-topic-ideas-access-v1", JSON.stringify(topic));
    window.dispatchEvent(new CustomEvent("projectready:session-ready", {detail: credential}));
    return credential;
  }

  window.ProjectReadySessionBootstrap = {
    ready: activate().catch((error) => {
      console.warn("Authorised session activation failed.", error);
      return null;
    }),
  };
})();
