# Home Hero Heading Line Spacing Update

Updated the home page hero heading so it uses the same tight heading rhythm as the Chapter Strengthener page.

## Files amended

- `app/static/landing.css`
- `app/static/landing - Copy.css`
- `app/static/projectready-suite.css`
- `tests/test_projectready_navigation_and_heading_ui.py`

## Behaviour

The home page `<h1>` now uses:

- `line-height: 1.02`
- `letter-spacing: -0.045em`
- `font-size: clamp(2.1rem, 4.8vw, 4.8rem)`
- `text-wrap: balance`

This matches the tighter visual rhythm used in the Chapter Strengthener hero heading.
