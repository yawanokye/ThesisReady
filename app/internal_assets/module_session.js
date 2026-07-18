(() => {
  "use strict";
  const scriptUrl = new URL(document.currentScript?.src || window.location.href, window.location.origin);
  const portalBase = scriptUrl.pathname.replace(/\/module-session\.js$/, "").replace(/\/$/, "");
  const declaredModulePath = document.querySelector('meta[name="projectready-internal-module-path"]')?.content || window.location.pathname;
  const modulePath = String(declaredModulePath || window.location.pathname).replace(/\/$/, "");

  window.ProjectReadyInternalPortal = Object.freeze({
    active: true,
    basePath: portalBase,
    modulePath,
  });

  function preservePrivateModuleLinks() {
    const routes = new Map([
      ["/workspace", `${portalBase}/workspace`],
      ["/chapter-strengthener", `${portalBase}/chapter-strengthener`],
      ["/strengthen-chapter", `${portalBase}/chapter-strengthener`],
      ["/topic-ideas", `${portalBase}/topic-ideas`],
      ["/ideas", `${portalBase}/topic-ideas`],
    ]);
    document.querySelectorAll("a[href]").forEach((anchor) => {
      try {
        const url = new URL(anchor.getAttribute("href"), window.location.origin);
        if (url.origin !== window.location.origin || !routes.has(url.pathname)) return;
        const privatePath = routes.get(url.pathname);
        anchor.setAttribute("href", `${privatePath}${url.search}${url.hash}`);
      } catch (_error) {}
    });
  }

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
      provider: data.provider || "internal_admin",
      product_area: "all",
      chapter_number: 0,
      saved_at: new Date().toISOString(),
    };
    window.ProjectReadyInternalCredential = credential;
    const prefix = "projectready-entitlement:";
    const areas = ["all", "thesis_workspace", "chapter_strengthener", "topic_ideas"];
    for (const area of areas) {
      for (const chapter of [0, 1, 2, 3, 4, 5, 6, 7, 99]) {
        try { localStorage.setItem(`${prefix}internal:${area}:chapter-${chapter}`, JSON.stringify(credential)); } catch (_error) {}
      }
    }
    try { localStorage.setItem(`${prefix}purchase:${data.purchase_id}`, JSON.stringify(credential)); } catch (_error) {}
    const topic = {...credential, access_id: "authorised-session"};
    try { sessionStorage.setItem("projectready-topic-ideas-access-v1", JSON.stringify(topic)); } catch (_error) {}
    try { localStorage.setItem("projectready-topic-ideas-access-v1", JSON.stringify(topic)); } catch (_error) {}
    preservePrivateModuleLinks();
    window.dispatchEvent(new CustomEvent("projectready:session-ready", {detail: credential}));
    return credential;
  }

  document.addEventListener("DOMContentLoaded", preservePrivateModuleLinks);
  window.ProjectReadySessionBootstrap = {
    ready: activate().catch((error) => {
      console.warn("Authorised session activation failed.", error);
      return null;
    }),
  };
})();
