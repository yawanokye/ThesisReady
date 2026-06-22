# Frontend Payment and Registration Access Update

This build now shows a clear registration or payment prompt whenever chapter drafting, revision, compliance checking, or export returns HTTP 401 or 402.

## Updated files

1. `app/static/app.js`
   - Handles HTTP 401 and 402 responses visibly.
   - Opens the registration/payment access gate.
   - Shows a persistent inline fallback notice in the workspace.
   - Prevents repeated draft submissions while an access check is running.
   - Restores the draft button after success or failure.
   - Displays Paystack GHS and international USD chapter prices when available.

2. `app/static/workspace.html`
   - Adds the visible registration/payment-required notice and action buttons.
   - Updates static asset version strings to prevent stale browser caching.

3. `app/static/projectready_payments.js`
   - Adds a registration-or-payment access modal.
   - Keeps direct secure checkout available.
   - Prefills checkout email and country from the saved registration profile.
   - Shows GHS pricing for African billing countries and USD pricing elsewhere.
   - Preserves project and chapter details when sending a user to registration.

4. `app/static/projectready_payments.css`
   - Styles the access modal, checkout modal, and inline fallback notice.
   - Adds responsive mobile layouts.

5. `app/static/register.js`
   - Returns the user to the correct project and chapter after registration.
   - Adds a `registered=1` confirmation flag.
   - Loads an existing saved registration profile for review or editing.

6. `app/static/register.html`
   - Updates the registration script version to prevent stale caching.

7. `app/main.py`
   - Fixes `/register` so it serves `register.html` instead of incorrectly opening the workspace.

8. `app/routers/payments.py`
   - Adds the configured Paystack GHS price to the plans API response for frontend display.

## Expected behaviour

- A successful project creation still returns HTTP 200.
- A paid chapter request without entitlement returns HTTP 402.
- The frontend now immediately shows:
  - `Register / create profile`
  - `Continue to payment`
  - `Not now`
- Repeated clicks no longer send multiple draft requests while the first request is pending.
- After registration, the user returns to the same workspace project and selected chapter.
- Selecting Ghana or another African billing country displays the configured Paystack GHS amount.

## Validation completed

- Python test suite: 8 tests passed.
- Python modules compiled successfully.
- `app.js`, `projectready_payments.js`, and `register.js` passed Node syntax checks.
- `/register`, `/workspace`, and `/api/payments/plans` were checked with FastAPI TestClient.

The current registration feature stores a workspace profile in the user's browser. It is not yet a full password-based authentication system.
