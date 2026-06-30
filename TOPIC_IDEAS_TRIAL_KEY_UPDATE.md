# Topic Ideas Trial Key Update

## Purpose

This update adds a private administrator trial key so the Topic Ideas unlock can be tested without making another Paystack or Stripe payment and without already having a Purchase ID.

## How it works

1. Set `PROJECTREADY_TOPIC_IDEAS_TRIAL_KEY` in the Render environment.
2. Open Topic Ideas and expand **Administrator trial access**.
3. Enter the payment or administrator email and the private trial key.
4. ProjectReady AI creates a Purchase ID automatically.
5. The server creates and activates a normal `topic_ideas_access` entitlement.
6. The browser receives the same Purchase ID and opaque access token used by paid access.
7. The 5, 8, 10 and 12 options become available.
8. One successful full generation consumes the trial entitlement exactly like a paid entitlement.

## Security controls

- The trial key is read only from the environment and is never written to the database or returned to the browser.
- Constant-time key comparison is used.
- A SHA-256 fingerprint, not the raw key, is used to enforce one-customer assignment.
- The same email can reuse the key only to restore a lost browser credential.
- A different email cannot claim the same key.
- Removing the environment variable disables the trial endpoint and hides the trial panel.

## Important scope

The trial validates ProjectReady AI's internal purchase record, access token, entitlement status, option unlocking and one-use generation consumption. It bypasses the external Paystack or Stripe checkout, so a final live-provider callback test is still required after the internal flow is confirmed.

## Render variable

```env
PROJECTREADY_TOPIC_IDEAS_TRIAL_KEY=use-a-private-random-value-of-at-least-12-characters
```

Delete or rotate the variable after testing.
