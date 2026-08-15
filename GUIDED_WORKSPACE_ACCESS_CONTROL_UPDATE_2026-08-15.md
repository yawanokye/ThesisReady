# ProjectReady Guided Workspace and Access Control Upgrade

Release date: 15 August 2026

## Student-facing simplification

### Thesis Workspace
- Full chapter draft development remains the primary action.
- The main content is presented as one standalone chapter-generation form.
- A sticky left research-journey sidebar now shows seven stages: project profile, chapter selection, chapter details, evidence/alignment, access, chapter development, and review/export.
- The sidebar marks completed/current steps and updates as the student works.
- The previous Research Cockpit remains available to the application logic, while progress is surfaced in the simpler sidebar for day-to-day use.
- Commercial/payment status is moved to the sidebar. The old payment panel remains in the DOM for checkout compatibility but is hidden in the guided layout.
- Students can enter a complimentary token directly in the sidebar.

### Chapter Strengthener
- The Strengthener now uses the same left-guided pattern.
- The existing chapter/revision controls remain a standalone main form.
- The large optional section-selection area is collapsed by default.
- Previous-chapter/full-work alignment is collapsed by default.
- Supervisor comments and literature support are grouped into one optional expandable area.
- The sidebar shows chapter source, chapter/scope, research logic, strengthening direction, optional support, access, and review/export.
- Complimentary token balance and current access mode are visible in the sidebar.

## Restricted developer access controls

The existing private internal developer portal now includes a Research Workspace Access Mode panel. The controls are server-side and stored in the shared ProjectReady database, so web and worker processes use the same policy.

Three modes are available:

1. **Normal commercial mode**
   - Keeps normal payment behaviour.
   - Keeps the configured Free Starter where applicable.

2. **Temporary Open Access**
   - Developer chooses an expiry window from 1 hour to 7 days.
   - Thesis Workspace and Chapter Strengthener protected actions bypass payment during the window.
   - Topic Ideas also respects Temporary Open Access.
   - The policy automatically returns to commercial mode after expiry.

3. **Payment Required**
   - Disables the Thesis Workspace Free Starter.
   - Paid access still works.
   - Restricted internal developer access still works.
   - Valid complimentary tokens still work.

## Complimentary page-credit tokens

The restricted portal can create complimentary access tokens with:
- recipient/purpose label
- optional assigned email
- module scope: Thesis Workspace, Chapter Strengthener, or both
- page-credit limit
- expiry in days

Security and enforcement:
- The raw token is displayed only once at creation.
- Only a SHA-256 token hash is stored in the database.
- Tokens can be revoked from the restricted portal.
- Assigned-email tokens require the matching email to be supplied.
- Module-scoped tokens cannot be used in another module.
- Generation/strengthening reserves the selected maximum page target against the token balance.
- A request exceeding the remaining balance is rejected and the student is told to reduce the custom page target or use paid access.
- Compliance review and export can use an active complimentary token without consuming additional page credits.
- Failed or cancelled background jobs return reserved complimentary page credits.
- Successful generation consumes the reserved page credits.
- Token usage is recorded server-side with project, chapter, action and status.

## New backend components

- `app/access_control.py`
- `app/routers/access.py`
- protected-access integration in `app/payments/guard.py`
- background-job reservation and rollback integration
- worker completion/rollback integration
- restricted developer portal policy/token endpoints

## Public access headers

The frontend sends these only when a complimentary credential is stored:

```text
X-ProjectReady-Complimentary-Token
X-ProjectReady-Complimentary-Email
```

Production CORS configuration now accepts these headers.

## Validation

- Python compilation: passed
- JavaScript syntax checks: passed
- HTML structure checks: passed
- Public `/static` Python-source exposure check: passed
- Full automated suite: **162/162 tests passed**
- Restricted portal end-to-end access-policy/token test: passed
