(() => {
  "use strict";

  const viewer = document.querySelector("[data-guide-viewer]");
  if (!viewer) return;

  const slides = Array.from(viewer.querySelectorAll("[data-guide-slide]"));
  const thumbs = Array.from(viewer.querySelectorAll("[data-guide-thumb]"));
  const jumpButtons = Array.from(viewer.querySelectorAll("[data-guide-jump]"));
  const previousButton = viewer.querySelector("[data-guide-prev]");
  const nextButton = viewer.querySelector("[data-guide-next]");
  const counter = viewer.querySelector("[data-guide-counter]");
  const openLink = viewer.querySelector("[data-guide-open]");
  const total = slides.length;
  let currentPage = 1;

  const clampPage = (page) => Math.min(total, Math.max(1, Number(page) || 1));

  const activeRangeContains = (button, page) => {
    const [start, end] = String(button.dataset.guideRange || "").split("-").map(Number);
    return Number.isFinite(start) && Number.isFinite(end) && page >= start && page <= end;
  };

  const showPage = (requestedPage, options = {}) => {
    const page = clampPage(requestedPage);
    currentPage = page;

    slides.forEach((slide) => {
      const active = Number(slide.dataset.guideSlide) === page;
      slide.hidden = !active;
      slide.setAttribute("aria-hidden", active ? "false" : "true");
    });

    thumbs.forEach((thumb) => {
      const active = Number(thumb.dataset.guideThumb) === page;
      thumb.classList.toggle("is-active", active);
      thumb.setAttribute("aria-current", active ? "true" : "false");
      if (active && options.scrollThumb !== false) {
        thumb.scrollIntoView({ behavior: options.instant ? "auto" : "smooth", block: "nearest", inline: "center" });
      }
    });

    jumpButtons.forEach((button) => {
      const active = activeRangeContains(button, page);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });

    if (counter) counter.textContent = `Page ${page} of ${total}`;
    if (previousButton) previousButton.disabled = page === 1;
    if (nextButton) nextButton.disabled = page === total;
    if (openLink) openLink.href = `/static/guides/annotated-html/pages/page-${String(page).padStart(2, "0")}.webp`;
  };

  previousButton?.addEventListener("click", () => showPage(currentPage - 1));
  nextButton?.addEventListener("click", () => showPage(currentPage + 1));

  thumbs.forEach((thumb) => {
    thumb.addEventListener("click", () => showPage(thumb.dataset.guideThumb));
  });

  jumpButtons.forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.guideJump));
  });

  viewer.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPage(currentPage - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showPage(currentPage + 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      showPage(1);
    } else if (event.key === "End") {
      event.preventDefault();
      showPage(total);
    }
  });

  showPage(1, { instant: true, scrollThumb: false });
})();
