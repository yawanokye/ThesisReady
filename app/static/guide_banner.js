(() => {
  "use strict";
  const body = document.body;
  if (!body) return;
  const moduleKey = String(body.dataset.guideModule || "").trim();
  if (!moduleKey) return;

  const configurations = {
    "topic-ideas": {
      title: "Using Topic Ideas for the first time?",
      text: "See which fields are required, strongly recommended or optional before generating a new set of ideas.",
      section: "topic-ideas"
    },
    "thesis-workspace": {
      title: "Using Thesis Workspace for the first time?",
      text: "Review the six-stage workflow before creating a project or developing a chapter working draft.",
      section: "thesis-workspace"
    },
    "chapter-strengthener": {
      title: "Using Chapter Strengthener for the first time?",
      text: "Review the difference between complete-chapter and selected-section revision before uploading your work.",
      section: "chapter-strengthener"
    }
  };
  const config = configurations[moduleKey];
  if (!config) return;

  const storageKey = `projectready-guide-banner-dismissed:${moduleKey}:v1`;
  try {
    if (window.localStorage.getItem(storageKey) === "1") return;
  } catch (_) {
    // Storage is optional. The banner can still be dismissed for the current page view.
  }

  const banner = document.createElement("section");
  banner.className = "guide-first-visit-banner";
  banner.setAttribute("aria-label", "First-visit user guidance");
  banner.innerHTML = `
    <div class="guide-first-visit-copy">
      <strong>${config.title}</strong>
      <span>${config.text}</span>
    </div>
    <div class="guide-first-visit-actions">
      <a href="/user-guide#video">Watch video</a>
      <a href="/user-guide#${config.section}">Open module guide</a>
      <button type="button" class="guide-first-visit-dismiss">Dismiss</button>
    </div>`;

  const dismiss = () => {
    try { window.localStorage.setItem(storageKey, "1"); } catch (_) {}
    banner.remove();
  };
  banner.querySelector(".guide-first-visit-dismiss")?.addEventListener("click", dismiss);

  const hero = document.querySelector(".topic-hero, header.hero, main .hero");
  if (hero && hero.parentNode) {
    hero.insertAdjacentElement("afterend", banner);
  } else {
    const topbar = document.querySelector(".workspace-topbar, .topbar, .site-header");
    if (topbar && topbar.parentNode) topbar.insertAdjacentElement("afterend", banner);
    else body.prepend(banner);
  }
})();
