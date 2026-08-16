(() => {
  "use strict";
  const body = document.body;
  if (!body) return;
  const moduleKey = String(body.dataset.guideModule || "").trim();
  if (!moduleKey) return;
  const configurations = {
    "topic-ideas": { title: "Using Topic Ideas for the first time?", text: "See the inputs, feasibility checks and responsible-use guidance before generating research ideas.", section: "architecture" },
    "thesis-workspace": { title: "Using the Research Journey for the first time?", text: "See the 12-stage journey, Research Record, evidence workflow, chapter development, analysis and final audit.", section: "research-journey" },
    "chapter-strengthener": { title: "Using Review & Strengthen for the first time?", text: "See how to strengthen existing work, resolve citation gaps and apply supervisor corrections without inventing evidence.", section: "review-strengthen" },
    "research-coach": { title: "Using Research Coach for the first time?", text: "See when to use Explain, Guide me, Help me decide and Viva preparation.", section: "research-coach" },
    "my-projects": { title: "Returning to a saved research project?", text: "See how My Research Projects supports recovery, continuity and the next required research step.", section: "my-projects" },
    "data-analysis": { title: "Using Data & Analysis for the first time?", text: "Review the calculation-first workflow, method selection, assumptions, diagnostics and verified reporting before running a model.", section: "data-analysis" }
  };
  const config = configurations[moduleKey];
  if (!config) return;
  const storageKey = `projectready-guide-banner-dismissed:${moduleKey}:v3`;
  try { if (window.localStorage.getItem(storageKey) === "1") return; } catch (_) {}
  const banner = document.createElement("section");
  banner.className = "guide-first-visit-banner";
  banner.setAttribute("aria-label", "First-visit user guidance");
  banner.innerHTML = `<div class="guide-first-visit-copy"><strong>${config.title}</strong><span>${config.text}</span></div><div class="guide-first-visit-actions"><a href="/user-guide#video">Watch video</a><a href="/user-guide#${config.section}">Open module guide</a><button type="button" class="guide-first-visit-dismiss">Dismiss</button></div>`;
  banner.querySelector(".guide-first-visit-dismiss")?.addEventListener("click", () => { try { window.localStorage.setItem(storageKey, "1"); } catch (_) {} banner.remove(); });
  const hero = document.querySelector(".topic-hero, header.hero, main .hero, .coach-hero, .projects-hero, .analysis-hero");
  if (hero?.parentNode) hero.insertAdjacentElement("afterend", banner);
  else document.querySelector(".workspace-topbar, .topbar, .site-header, header")?.insertAdjacentElement("afterend", banner) || body.prepend(banner);
})();
