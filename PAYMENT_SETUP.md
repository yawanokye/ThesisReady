# ProjectReady AI payment deployment

The application now sells access per project chapter.

| Plan | Public price | Included for the purchased chapter |
|---|---:|---|
| Free Starter | US$0 | One Chapter One draft, up to five selected sections |
| Bachelors Project | US$4.99 | One draft, one revision, one compliance check, one DOCX export |
| Masters Dissertation / MPhil Thesis | US$9.99 | One draft, one revision, one compliance check, one DOCX export |
| Professional Doctorate / PhD | US$19.99 | One draft, one revision, one compliance check, one DOCX export |

Paid access is tied to the saved project ID and chapter number. It expires after 90 days. African billing countries are routed to Paystack. Other billing countries are routed to Stripe.

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Add a Render PostgreSQL database

Create a PostgreSQL database in Render and connect it to the ProjectReady web service. Set the database's **internal connection URL** as:

```text
DATABASE_URL=<Render PostgreSQL internal URL>
```

The project and payment tables are created automatically when the service starts.

For local development, leave `DATABASE_URL` empty and set:

```text
PROJECTREADY_SQLITE_DB_PATH=projectready.db
PROJECTREADY_SQLITE_PAYMENT_DB=projectready.db
```

## 3. Set Render environment variables

```text
APP_BASE_URL=https://projectreadyai.com
PROJECTREADY_PAYMENT_SUCCESS_PATH=/workspace
PROJECTREADY_PAYMENT_CANCEL_PATH=/workspace

PAYSTACK_SECRET_KEY=<Paystack live secret key>
STRIPE_SECRET_KEY=<Stripe live secret key>
STRIPE_WEBHOOK_SECRET=<Stripe webhook signing secret>
```

Choose one Paystack pricing method.

### Recommended: fixed GHS prices

```text
PROJECTREADY_PAYSTACK_BACHELORS_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_MASTERS_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_DOCTORATE_GHS=<approved GHS price>
```

### Alternative: configured USD-to-GHS conversion

Leave the three fixed GHS fields empty and set:

```text
PROJECTREADY_PAYSTACK_USD_TO_GHS_RATE=<approved rate>
```

The public plan remains priced in USD, but Paystack receives the configured GHS charge.

## 4. Configure Paystack

Use this callback URL:

```text
https://projectreadyai.com/payment/paystack/callback
```

Use this webhook URL:

```text
https://projectreadyai.com/payment/paystack/webhook
```

The application activates access only after it verifies the transaction status, reference, amount, currency, and customer email.

## 5. Configure Stripe

Create a webhook endpoint:

```text
https://projectreadyai.com/payment/stripe/webhook
```

Subscribe it to:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
```

Copy the endpoint signing secret into `STRIPE_WEBHOOK_SECRET`.

## 6. Deploy and test

1. Deploy with Paystack and Stripe test keys first.
2. Create a test project and confirm that one free Chapter One draft works with five or fewer selected sections.
3. Confirm that Chapter Two returns the checkout prompt before payment.
4. Complete a Paystack test payment using an African billing country.
5. Complete a Stripe test payment using a non-African billing country.
6. Confirm that the purchased chapter allows exactly one draft, one revision, one compliance check, and one DOCX export.
7. Switch to live provider keys only after both test flows pass.

Do not place secret keys in JavaScript, HTML, GitHub, or the public Render environment preview. Keep them in Render's secret environment variables.
