# Topic Ideas new-job state isolation update

The Topic Ideas page no longer restores an old research form after an ordinary browser refresh.

## Behaviour

- The clear control is now labelled **Clear and start new job**.
- It clears the research area, context, country/region, keywords, trend focus, outputs, source records and pending form draft.
- It preserves the payment email, selected billing market and valid paid-access credential.
- A running generation request is cancelled when the user clears or starts another generation.
- A late response from an older request cannot overwrite the current job.
- Form details are saved only for the payment checkout journey and are restored once after the user returns from Paystack or Stripe.
- Checkout form recovery expires after two hours and is deleted after restoration.
- The Topic Ideas form uses `autocomplete="off"` to reduce browser autofill of old research details.

No new environment variable is required.
