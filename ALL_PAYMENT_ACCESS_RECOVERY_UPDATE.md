# All-payment access recovery update

## Purpose

ProjectReady AI now provides a support-controlled recovery workflow for every payment product:

- Topic Ideas
- Thesis Workspace chapter development
- Chapter Strengthener revision-only access

A customer no longer needs to know the internal Purchase ID before support can locate a valid payment. Support can search by the exact payment email alone, or narrow the search using an internal Purchase ID, ProjectReady provider reference, or Stripe Checkout Session ID.

## Recovery workflow

1. Open `/admin/payment-recovery`.
2. Enter `PROJECTREADY_SUPPORT_RECOVERY_KEY` and the customer's exact payment email.
3. Optionally enter the payment ID/reference supplied by the customer.
4. Review the matching payment records and select the correct paid purchase.
5. Create a one-time recovery link.
6. Send the link to the verified customer.
7. The customer's browser redeems the link and stores a fresh access credential for the correct ProjectReady AI product.

## Security and integrity

- Exact email matching is required.
- The support API requires a private environment key with at least 16 characters.
- Search results never return access tokens.
- Recovery links expire after 60 minutes and work once.
- Access-token rotation invalidates the previous browser credential.
- Recovery does not reset quotas, extend expiry or create an unpaid entitlement.
- Pending records are verified directly with Paystack or Stripe before a recovery link can be issued.
- Recovery-link creation and redemption are recorded in an audit table.

## New routes

- `GET /admin/payment-recovery`
- `GET /payment/recover`
- `POST /api/admin/payment-recovery/search`
- `POST /api/admin/payment-recovery/create-link`
- `POST /api/payments/redeem-recovery`

## Files updated

- `app/payments/store.py`
- `app/routers/payments.py`
- `app/main.py`
- `app/static/payment_recovery_admin.html`
- `app/static/payment_recovery_admin.js`
- `app/static/payment_recovery.css`
- `app/static/payment_recover.html`
- `app/static/payment_recover.js`
- `.env.example`
- `PAYMENT_SETUP.md`
- `tests/test_all_payment_recovery.py`
