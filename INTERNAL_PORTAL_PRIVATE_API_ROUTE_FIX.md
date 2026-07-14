# Restricted portal private API route fix

The portal assets now call session, module-access and job endpoints beneath the configured private portal path instead of relying on the public-looking `/api/internal/*` route family.

Example when `PROJECTREADY_INTERNAL_PORTAL_PATH=/internal/anovlad`:

- `GET /internal/anovlad/api/session`
- `POST /internal/anovlad/api/session`
- `DELETE /internal/anovlad/api/session`
- `POST /internal/anovlad/api/module-access`
- `GET /internal/anovlad/api/jobs`

The former `/api/internal/*` routes remain registered as backward-compatible aliases, but the browser no longer depends on them. Asset version identifiers were raised to `commercial-v3` to bypass cached JavaScript.

Files amended:

- `app/internal_portal.py`
- `app/internal_assets/portal.html`
- `app/internal_assets/portal.js`
- `app/internal_assets/module_session.js`
- `tests/test_internal_developer_entitlement.py`
