# Topic Ideas payment update

ProjectReady AI now requires one-time access before generating Topic Ideas.

## Prices

- Ghana: **GHS 10.00**, paid through Paystack.
- Outside Ghana: **US$1.50**, paid through Stripe.

## What one purchase includes

- One topic-idea generation request.
- Up to 12 proposed topic ideas.
- Level-appropriate general and specific objectives.
- Trend-grounded scholarly metadata records.
- Possible data-source and instrument-source suggestions.
- A 30-day window in which to use the single generation credit.

The credit is reserved only while generation runs. If generation fails, the credit is returned automatically. Once a successful result is produced, the credit is consumed.

## Render environment variables

```env
PROJECTREADY_TOPIC_IDEAS_USD=1.50
PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS=10.00
```

Existing Paystack, Stripe, webhook, APP_BASE_URL and persistent database settings remain required.

## New routes

- `GET /api/topic-ideas/access-plan`
- `POST /api/topic-ideas/checkout`
- `POST /api/topic-ideas`, now protected by a paid one-use entitlement
