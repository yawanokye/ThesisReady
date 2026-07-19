# ProjectReady AI User Guidance Centre Update

Implemented on 19 July 2026.

## Added

- Public `/user-guide` guidance centre and `/how-to-use` alias.
- Privacy-enhanced YouTube walkthrough embed using `youtube-nocookie.com`.
- Stable public copy of the current annotated guide PDF.
- Module-specific mandatory, strongly recommended, optional and conditional field guidance.
- Contextual help cards on Topic Ideas, Thesis Workspace and Chapter Strengthener.
- First-visit dismissible guidance banner on all three modules.
- User Guide navigation links on the homepage, module pages, policy pages and restricted portal dashboard.
- Homepage hero and footer links to the guidance centre.

## First-visit storage

The banner stores only a module-specific dismissal flag:

- `projectready-guide-banner-dismissed:topic-ideas:v1`
- `projectready-guide-banner-dismissed:thesis-workspace:v1`
- `projectready-guide-banner-dismissed:chapter-strengthener:v1`

It does not store, restore or modify research form entries.

## Public assets

- `/static/guides/projectready-ai-annotated-user-guide.pdf`
- `/static/user_guide.css`
- `/static/user_guide_shared.css`
- `/static/guide_banner.js`

## Package hygiene completed

- Removed obsolete backend Python copies from the publicly served `app/static` directory.
- Removed obsolete Stripe test-mode regression tests because the commercial build uses live payment routing.
- Removed obsolete Topic Ideas trial-key tests because the public trial-key path is no longer part of the commercial build.
