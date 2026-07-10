# Internal Developer Entitlement Update

This update adds non-payment developer access for ProjectReady AI without restoring public trial payments.

## What changed

Internal access now requires two checks:

1. The developer email must be listed in `PROJECTREADY_INTERNAL_ACCESS_EMAILS`.
2. The developer must enter the configured six-digit internal key.

A successful check returns a signed, time-limited credential that the existing entitlement guard accepts across:

- Topic Ideas
- Thesis Workspace
- Chapter Strengthener

The credential does not create a Paystack or Stripe transaction and does not consume a normal customer quota.

## Environment variables

```env
PROJECTREADY_INTERNAL_ACCESS_EMAILS=aadam@ucc.edu.gh
PROJECTREADY_INTERNAL_ACCESS_KEY=123456
PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256=
PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET=
PROJECTREADY_INTERNAL_ACCESS_HOURS=12
```

For production, prefer `PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256` instead of storing the plain six-digit key. Generate it with:

```bash
echo -n '123456' | sha256sum
```

Set `PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET` to a long random secret if available.

## Backend files amended

- `app/payments/internal_access.py`
- `app/payments/guard.py`
- `app/routers/payments.py`
- `app/routers/topic_ideas.py`
- `app/routers/generation.py`

## Frontend files amended

- `app/static/projectready_payments.js`
- `app/static/topic_ideas.html`
- `app/static/topic_ideas.js`

## New endpoint

```text
POST /api/payments/internal-access
```

Request:

```json
{
  "email": "aadam@ucc.edu.gh",
  "key": "123456",
  "product_area": "thesis_workspace",
  "project_id": "project-id",
  "chapter_number": 2,
  "chapter_title": "Literature Review"
}
```

Supported `product_area` values:

- `thesis_workspace`
- `chapter_strengthener`
- `topic_ideas`
- `all`

## Security note

Do not use a public trial key. Internal access is intentionally time-limited and tied to the allow-listed developer email plus the six-digit key.
