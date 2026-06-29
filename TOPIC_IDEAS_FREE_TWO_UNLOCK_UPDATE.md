# Topic Ideas: 2 free, unlock up to 12

This build changes the Topic Ideas funnel from payment-first to preview-first.

- Free users receive 2 complete ideas.
- The result page displays an unlock prompt after the free results.
- Ghana unlock price remains GHS 10 through Paystack.
- International unlock price remains US$1.50 through Stripe.
- Paid users can select 5, 8, 10 or 12 ideas.
- The paid entitlement remains one successful generation, valid for 30 days.
- Research form values are saved locally before checkout and restored after payment.
- The server enforces the 2-idea free limit and 12-idea paid maximum.

## Files updated

- `app/routers/topic_ideas.py`
- `app/topic_ideas_service.py`
- `app/routers/payments.py`
- `app/payments/entitlements.py`
- `app/payments/stripe_provider.py`
- `app/static/topic_ideas.html`
- `app/static/topic_ideas.js`
- `app/static/topic_ideas.css`
- `app/static/index.html`
- `app/static/workspace.html`
- `tests/test_topic_ideas_payment.py`
- `PAYMENT_SETUP.md`
- `TOPIC_IDEAS_PAYMENT_UPDATE.md`

## Validation

- Python compilation passed.
- Frontend JavaScript syntax check passed.
- Full automated test suite passed: **45 tests**.
