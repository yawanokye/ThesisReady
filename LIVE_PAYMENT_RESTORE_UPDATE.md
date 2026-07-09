# Live payment restoration update

This update removes internal trial-payment access from ProjectReady AI and restores production payment routing.

## What changed

- Ghana and other African billing countries route to Paystack.
- Non-African billing countries route to Stripe.
- Stripe is live-only in this production package.
- The administrator Topic Ideas trial-payment panel was removed.
- The `/api/topic-ideas/activate-trial` endpoint was removed.
- Checkout payloads no longer accept `test_access_key`.
- Paid-user entitlement recovery remains available through payment email and Purchase ID.

## Files amended

- `app/payments/router.py`
- `app/payments/stripe_provider.py`
- `app/routers/payments.py`
- `app/static/projectready_payments.js`
- `app/static/projectready_payments.css`
- `app/static/topic_ideas.html`
- `app/static/topic_ideas.js`
- `app/static/topic_ideas.css`
- `app/static/index.html`
- `app/static/index - Copy.html`
- `app/static/chapter_strengthener.html`
- `app/static/workspace.html`
- `.env.example`
- `PAYMENT_SETUP.md`
- `tests/test_live_payment_routing.py`
- `tests/test_topic_ideas_unlock_recovery.py`

## Required production environment variables

```env
APP_BASE_URL=https://projectreadyai.com
DATABASE_URL=/var/data/projectready.db

PAYSTACK_SECRET_KEY=sk_live_...
PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS=10.00
PROJECTREADY_PAYSTACK_BACHELORS_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_MASTERS_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_DOCTORATE_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_BACHELORS_REVISION_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_MASTERS_REVISION_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_DOCTORATE_REVISION_GHS=<approved GHS price>

STRIPE_LIVE_SECRET_KEY=sk_live_...
STRIPE_LIVE_WEBHOOK_SECRET=whsec_...
```

Do not set any trial-payment or forced test-routing variables on the live service.
