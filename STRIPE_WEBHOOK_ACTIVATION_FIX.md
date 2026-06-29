# Stripe webhook activation fix

## Problem

Stripe successfully completed Checkout, but `checkout.session.completed` returned HTTP 500 with:

```json
{"ok": false, "message": "0"}
```

The payment itself was valid. The failure occurred while ProjectReady AI converted or re-retrieved Stripe SDK objects before updating the purchase entitlement.

## Fix

- Converts Stripe SDK objects defensively, with a mapping fallback when recursive conversion fails.
- Uses the already authenticated Checkout Session contained in the signed webhook event.
- Removes the unnecessary second Stripe API request during webhook fulfilment.
- Locates the purchase by provider reference, purchase ID, or Checkout Session ID.
- Verifies payment status, amount, currency, email, project ID, and purchase ID.
- Keeps activation idempotent, so Stripe can safely resend the same event.
- Returns descriptive exception types instead of the unhelpful message `0`.

## Webhook endpoint

```text
https://projectreadyai.com/payment/stripe/webhook
```

After deployment, resend the failed `checkout.session.completed` event from Stripe Workbench. A successful response should be HTTP 200 with `activated: true`.
