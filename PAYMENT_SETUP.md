# ProjectReady AI payment deployment

The application now sells access per project chapter.

| Plan | Public price | Included for the purchased chapter |
|---|---:|---|
| Free Starter | US$0 | One Chapter One draft, up to five selected sections |
| Bachelors Project | US$4.99 | One guided working draft, one strengthening revision, one compliance review, one editable DOCX export |
| Masters Dissertation / MPhil Thesis | US$9.99 | One guided working draft, one strengthening revision, one compliance review, one editable DOCX export |
| Professional Doctorate / PhD | US$19.99 | One guided working draft, one strengthening revision, one compliance review, one editable DOCX export |

Paid access is tied to the saved project ID and chapter number. It expires after 90 days. African billing countries are routed to Paystack. Other billing countries are routed to Stripe.


## Topic Ideas access

Topic Ideas provides a two-idea free preview. Payment unlocks one full generation credit rather than a chapter entitlement.

| Billing market | Price | Provider | Included |
|---|---:|---|---|
| Ghana | GHS 10.00 | Paystack | After 2 free ideas, unlock one generation of up to 12 ideas |
| Outside Ghana | US$1.50 | Stripe | After 2 free ideas, unlock one generation of up to 12 ideas |

Set:

```text
PROJECTREADY_TOPIC_IDEAS_USD=1.50
PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS=10.00
```

The credit remains available for 30 days and is consumed only after a successful generation. A failed generation automatically returns the credit.

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Configure durable database storage

### Simplest and lowest-cost Render setup

Attach a persistent disk to the existing ProjectReady AI web service and use:

```text
Mount path: /var/data
DATABASE_URL=/var/data/projectready.db
```

Both the main project database and the payment/entitlement store now honour this path. New project IDs, Stripe and Paystack purchase records, webhook events and usage credits therefore survive redeployments and restarts. Do not set `DATABASE_URL=projectready.db` for a commercial Render deployment because that file is stored in the temporary source directory.

### PostgreSQL option

For multiple web-service instances or heavier concurrency, create a Render PostgreSQL database and set its **internal connection URL** as `DATABASE_URL`.

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
6. Confirm that the purchased chapter allows exactly one guided working draft, one strengthening revision, one compliance review, and one editable DOCX export.
7. Switch to live provider keys only after both test flows pass.

Do not place secret keys in JavaScript, HTML, GitHub, or the public Render environment preview. Keep them in Render's secret environment variables.

## Revision-only chapter-strengthening prices

Users bringing a chapter from outside ProjectReady AI use a revision-only plan. Configure the USD prices if the defaults should be changed:

```text
PROJECTREADY_BACHELORS_REVISION_USD=2.99
PROJECTREADY_MASTERS_REVISION_USD=5.99
PROJECTREADY_DOCTORATE_REVISION_USD=11.99
```

Optional fixed Paystack GHS prices:

```text
PROJECTREADY_PAYSTACK_BACHELORS_REVISION_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_MASTERS_REVISION_GHS=<approved GHS price>
PROJECTREADY_PAYSTACK_DOCTORATE_REVISION_GHS=<approved GHS price>
```

The revision-only plan includes one strengthening revision, one compliance check and one DOCX export. It contains no initial draft credit.

## Topic Ideas payment-return activation

The Topic Ideas payment flow now uses three recovery layers so a successful payment cannot remain locked merely because browser storage was cleared or the customer returned through a different hostname.

1. The Stripe or Paystack callback verifies and activates the purchase.
2. The callback creates a short-lived, single-use server handoff code and returns the customer to `/topic-ideas`.
3. The Topic Ideas page redeems the handoff for a fresh opaque access credential and immediately enables the 5, 8, 10 and 12 idea options.

The page also checks a pending transaction directly with its original provider instead of depending only on webhook timing. A customer whose payment is already complete can use **Paid but the options are still locked?** with the payment email and Purchase ID to restore access.

The access handoff does not place the real access token in the URL. Only a hashed, expiring, single-use handoff is stored in the database.

No additional environment variable is required. The payment and handoff tables must remain on the persistent database configured by:

```env
DATABASE_URL=/var/data/projectready.db
```

## Topic Ideas administrator trial key

To test the internal Topic Ideas unlock before making another payment, temporarily set:

```env
PROJECTREADY_TOPIC_IDEAS_TRIAL_KEY=your-private-random-trial-key
```

The Topic Ideas page will show an **Administrator trial access** panel. The key creates a Purchase ID automatically and issues the same one-generation entitlement used by a paid purchase. The key is assigned to the first email that activates it. The same email may reuse it to restore a lost browser credential, but it does not reset a consumed generation. Remove or rotate the environment variable after the test.

This test bypasses the payment provider. It confirms the application unlock and entitlement path, not the Paystack or Stripe callback.


## Support recovery for all payments

Set a strong private environment variable:

```env
PROJECTREADY_SUPPORT_RECOVERY_KEY=replace-with-a-long-random-secret
```

Open the support dashboard at:

```text
https://projectreadyai.com/admin/payment-recovery
```

The dashboard searches the persistent payment database using the customer's exact payment email. A Purchase ID, ProjectReady provider reference or Stripe Checkout Session ID may be entered when available, but it is not required. Select the correct paid record and create a one-time recovery link. The customer opens the link on the device where access should be restored. The link expires after 60 minutes, works once and does not extend or reset the purchased quota.
