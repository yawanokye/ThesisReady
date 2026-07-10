# Workspace Plain Hero UI Update

This update restores the Thesis Workspace hero section to a plain card layout to match the Topic Ideas and Chapter Strengthener pages.

## Files amended

- `app/static/workspace-ui-clarity.css`
- `app/static/workspace.html`

## Changes

- Removed the blue gradient hero background on the Thesis Workspace page.
- Added a white card-style hero container with border, rounded corners and soft shadow.
- Applied Chapter Strengthener-style heading spacing, line height and letter spacing.
- Improved lead paragraph line spacing for readability.
- Hid the decorative hero divider on the Thesis Workspace hero only.
- Updated the CSS cache-busting query string in `workspace.html`.

The change is scoped to `body.thesis-suite .hero`, so Topic Ideas, Chapter Strengthener and other module pages are not affected.
