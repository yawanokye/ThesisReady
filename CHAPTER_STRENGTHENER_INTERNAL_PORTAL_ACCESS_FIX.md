# Chapter Strengthener internal portal access fix

This update makes restricted developer access authoritative on the server for Chapter Strengthener and the other protected modules.

## Corrections

- Validates the HttpOnly restricted portal cookie on every same-origin request.
- Protected actions accept the validated portal session even when localStorage or custom headers are unavailable.
- Keeps Chapter Strengthener on its private portal path after **Clear and start new job**.
- Keeps internal navigation links within the restricted portal.
- Stores explicit internal credentials for the Chapter Strengthener area as a browser compatibility fallback.
- Displays a clear internal-access status instead of a payment prompt.
- Preserves the restricted path when the new-job query parameter is removed.

No new environment variable is required.
