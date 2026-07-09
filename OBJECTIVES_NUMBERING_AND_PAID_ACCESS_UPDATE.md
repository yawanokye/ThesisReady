# Objectives Numbering and Paid Access Recovery Update

This update addresses two production issues observed in generated Chapter One drafts and in the paid entitlement flow.

## 1. Objectives and research questions formatting

- Research Objectives now restart their ordered list at 1 within the objectives section.
- Research Questions now restart their ordered list at 1 within the research questions section.
- The system prompt now instructs the model not to continue numbering from a previous list.
- Explanatory commentary after the last objective, question or hypothesis is no longer left as normal academic prose.
- If the commentary is useful as guidance, it is moved into a bracketed `[confirm ...]` attention note so the DOCX exporter colours it red.
- This prevents outputs such as research questions starting from 6 after five objectives.

## 2. Paid user entitlement recovery

Recommended production approach:

- Users should register or create a lightweight portal profile before payment.
- Each paid purchase should remain attached to the user's email, project, chapter and Purchase ID.
- The browser should still receive an opaque access token for immediate use.
- A backup restoration flow should allow a paid user to recover remaining entitlements with payment email and Purchase ID.

Implemented in this update:

- All successful payments now create a short-lived, one-time server handoff, not only Topic Ideas.
- The Thesis Workspace automatically redeems the handoff after payment and restores the chapter access token on the returning browser.
- A new endpoint `/api/payments/recover-access` restores paid access using payment email and Purchase ID.
- The access gate now includes an “Already paid? Restore access” panel.
- The same recovery pattern works for guided chapter development and revision-only paid access.

## 3. Why this design is better

A portal-only design is cleaner long-term, but it requires proper authentication, password reset or passwordless login, session management and user dashboard work. The current hybrid design gives immediate reliability now while preserving a path to a full registered user portal.

Recommended next phase:

- Add a paid-user dashboard listing active purchases, remaining draft/revision/compliance/export entitlements, expiry dates and download links.
- Use passwordless email OTP or magic-link login.
- Keep Purchase ID recovery as a support and self-service backup.
