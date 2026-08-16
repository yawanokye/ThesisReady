# Patch 1: Complimentary Token → Chapter Strengthener Continuity

Base: ProjectReady-Selected-Papers-Library-2026-08-15
Date: 2026-08-16

## Problem fixed
A student can use complimentary access for chapter development and later need Chapter Strengthener, but an existing token may have been issued for Thesis Workspace only or may have too few remaining page credits. Previously the developer had to revoke it and issue a new raw token.

## What changes
- Existing complimentary tokens can be topped up without changing the raw token already given to the student.
- Existing token scope can be changed to `all`, which means Thesis Workspace + Chapter Strengthener.
- Existing token expiry can be extended.
- Developer portal adds `Add pages`, `Use in both`, `Extend`, and `Revoke` actions.
- Raw token remains hashed in storage and is never redisplayed by the server.
- Page-credit enforcement remains server-side.

## Immediate use for the reported student
1. Deploy this patch and restart the web service.
2. Open the restricted developer portal.
3. Find the student's existing complimentary token by masked ID/label/email.
4. Click `Use in both` if it was Thesis Workspace-only.
5. Click `Add pages` if the remaining balance is too low for strengthening.
6. The student keeps using the same token code already supplied.

## Files replaced
- `app/access_control.py`
- `app/internal_portal.py`
- `app/internal_assets/portal.html`
- `app/internal_assets/portal.js`

The included test file is optional in production.

## Validation
Full suite on this patch: 178 passed.
