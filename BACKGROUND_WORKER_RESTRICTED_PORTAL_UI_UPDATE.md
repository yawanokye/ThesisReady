# Commercial background worker, restricted portal and workspace UI update

## Background processing

Long chapter drafting and Chapter Strengthener requests are now submitted to a durable database queue. The web service returns a job ID and private job token, while a separate worker performs the AI request, saves the result and completes or rolls back the reserved entitlement.

The browser polls the job status, displays progress, resumes after refresh and permits cancellation while a job is still queued or waiting to retry.

### Render services

Use the same codebase and the same PostgreSQL `DATABASE_URL` for both services.

**Web service start command**

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Background worker start command**

```bash
python -m app.jobs.worker
```

PostgreSQL is required for a commercial deployment with separate services. Local SQLite remains suitable only for local development and single-process testing.

## Restricted internal operations portal

The former developer-access controls have been removed from all public module pages and payment dialogs. The internal portal is served only through the private path configured in `PROJECTREADY_INTERNAL_PORTAL_PATH`. Its HTML, CSS and JavaScript are stored outside the public static directory.

The portal requires:

- an allow-listed email;
- the six-digit internal key;
- a signed, time-limited HttpOnly session cookie;
- the private portal path.

Login attempts are rate limited by hashed email and IP address. The portal and its assets return `noindex`, deny framing and use a restrictive Content Security Policy. The old direct internal-access API is disabled by default.

Use `PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256` in production instead of storing the six-digit key in plain text.

## Thesis Workspace interface

Optional setup fields are grouped in collapsed sections. Users see the essential profile fields first and can select **Show more optional fields** or open only the group they need. Additional guided questions under each selected chapter section are also collapsed.

## Important environment variables

```env
DATABASE_URL=postgresql://...
PROJECTREADY_BACKGROUND_JOBS_ENABLED=1
PROJECTREADY_JOB_MAX_ATTEMPTS=2
PROJECTREADY_WORKER_POLL_SECONDS=2
PROJECTREADY_WORKER_LEASE_SECONDS=2700
PROJECTREADY_WORKER_HEARTBEAT_SECONDS=90

PROJECTREADY_INTERNAL_PORTAL_PATH=/internal/a-private-random-path
PROJECTREADY_INTERNAL_ACCESS_EMAILS=developer@example.com
PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256=<sha256-of-six-digit-key>
PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET=<long-random-secret>
PROJECTREADY_INTERNAL_ACCESS_HOURS=12
PROJECTREADY_INTERNAL_LOGIN_MAX_ATTEMPTS=5
PROJECTREADY_INTERNAL_LOGIN_WINDOW_MINUTES=15
PROJECTREADY_COOKIE_SECURE=1
PROJECTREADY_ENABLE_LEGACY_INTERNAL_ACCESS_ENDPOINT=0
PROJECTREADY_EXPOSE_API_DOCS=0
```
