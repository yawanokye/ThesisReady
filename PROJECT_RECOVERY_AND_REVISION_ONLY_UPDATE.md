# Project recovery and revision-only pathway

## 1. Low-cost Project ID recovery

The app now uses a recovery email and a user-created 6-digit PIN. No transactional email provider is required.

### How it works

1. The user enters a recovery email and a 6-digit PIN when creating a project.
2. The PIN is never stored as plain text. It is stored as a salted PBKDF2-SHA256 hash.
3. If the Project ID is lost, the user enters the same email and PIN.
4. The app returns only matching project summaries and Project IDs.
5. Active paid-access credentials for the recovered projects are renewed for the current browser, allowing unused revision, compliance and export credits to be used after changing devices.
6. Recovery attempts are rate-limited.

Existing projects can enable or update recovery from the Thesis Workspace while the Project ID is still available. Renewing paid-access credentials invalidates the older browser token for the same purchase, which protects access when a device is lost.

### New routes

```text
POST /api/projects/recover
POST /api/projects/{project_id}/recovery
```

The public project-list endpoint is now protected by `PROJECTREADY_ADMIN_KEY`.

## 2. Revision-only pathway

The Chapter Strengthener now offers two entry options:

- Use a chapter already connected to ProjectReady AI.
- Upload a chapter written or received elsewhere.

For an external chapter, the app creates a lightweight revision project, stores the original chapter, enables email-and-PIN recovery, and offers a revision-only purchase.

### Revision-only package

- No initial chapter draft
- One comprehensive strengthening revision
- One compliance check
- One DOCX export
- 90-day access

### Default USD prices

| Level | Default price |
|---|---:|
| Bachelors | US$2.99 |
| Non-Research Masters / MPhil | US$5.99 |
| Professional Doctorate / PhD | US$11.99 |

The prices are configurable through environment variables.

### New route

```text
POST /api/chapter-strengthener/external-projects
```

### Payment plan keys

```text
bachelors_revision
masters_revision
doctorate_revision
```

Payment callbacks return the user to the page that started checkout. External revision purchases therefore return to `/chapter-strengthener` rather than the Thesis Workspace.

## 3. Deployment settings

```env
PROJECTREADY_RECOVERY_PBKDF2_ITERATIONS=150000
PROJECTREADY_RECOVERY_WINDOW_SECONDS=900
PROJECTREADY_RECOVERY_MAX_ATTEMPTS=6
PROJECTREADY_ADMIN_KEY=replace_with_a_long_random_admin_key

PROJECTREADY_BACHELORS_REVISION_USD=2.99
PROJECTREADY_MASTERS_REVISION_USD=5.99
PROJECTREADY_DOCTORATE_REVISION_USD=11.99

PROJECTREADY_PAYSTACK_BACHELORS_REVISION_GHS=
PROJECTREADY_PAYSTACK_MASTERS_REVISION_GHS=
PROJECTREADY_PAYSTACK_DOCTORATE_REVISION_GHS=
```

Fixed GHS amounts are optional. If they are blank, the existing configured USD-to-GHS rate is used.

## 4. Database changes

Startup automatically creates the `project_recovery` table. No manual migration command is required for the current SQLite-compatible database layer or PostgreSQL setup.

## 5. Validation completed

- Python files compile successfully.
- Frontend JavaScript passes syntax checking.
- All 26 automated tests pass.
