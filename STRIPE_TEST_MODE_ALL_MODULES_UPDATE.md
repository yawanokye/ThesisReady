# Stripe test mode for all paid ProjectReady AI modules

## Purpose

This update adds a guarded switch that routes Topic Ideas, Thesis Workspace and Chapter Strengthener through Stripe test mode without changing or deleting live credentials.

## Test settings

```text
PROJECTREADY_STRIPE_MODE=test
PROJECTREADY_FORCE_STRIPE=1
PROJECTREADY_STRIPE_TEST_CHECKOUT_KEY=<private random key>
STRIPE_TEST_SECRET_KEY=sk_test_...
STRIPE_TEST_WEBHOOK_SECRET=whsec_...
DATABASE_URL=/var/data/projectready-test.db
```

A separate staging Render service and test database are strongly recommended.

## Expected unlock results

| Pathway | Expected entitlement after successful Stripe test checkout |
|---|---|
| Topic Ideas | One generation of 5, 8, 10 or 12 ideas |
| Thesis Workspace | One draft, one strengthening revision, one compliance check and one DOCX export |
| Chapter Strengthener | One strengthening revision, one compliance check and one DOCX export |

## Safety controls

- Test and live Stripe keys are stored separately.
- The active key must match the selected environment.
- Test mode can force Stripe routing from Ghana.
- Every test checkout requires a private server-verified test key.
- Stripe session `livemode` is checked against the stored purchase environment.
- The test key is never exposed by the environment-status API.
- Live mode ignores the force-Stripe testing switch.
