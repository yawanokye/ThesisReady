# Chapter Strengthener internal access UI fix

This update restores a visible developer access route on the Chapter Strengthener page.

## What changed

- Added a collapsed **Developer access** panel directly below the Chapter Strengthener access summary.
- The panel requires both the allow-listed developer email and the six-digit internal access key.
- Chapter Strengthener now activates `chapter_strengthener` internal access even before a project is loaded or an external revision project is created.
- Internal credentials can now be saved as module-level credentials and reused when a project is later loaded or created.
- Payment headers and entitlement checks now look for Chapter Strengthener internal credentials as a fallback.

## Security position

This does not restore public trial access. The server still requires:

```env
PROJECTREADY_INTERNAL_ACCESS_EMAILS=...
PROJECTREADY_INTERNAL_ACCESS_KEY=...
PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET=...
```

The developer key is not enough without an allow-listed email.
