# Topic Ideas free preview and unlock update

ProjectReady AI now uses a freemium Topic Ideas journey.

## Customer journey

1. The user enters a research area and supporting details.
2. The platform generates the first **2 complete ideas free**.
3. A clear prompt offers a fuller set of up to **12 ideas** to compare and select from.
4. Ghana customers pay **GHS 10.00** through Paystack.
5. Customers outside Ghana pay **US$1.50** through Stripe.
6. After payment confirmation, the user chooses 5, 8, 10 or 12 ideas and uses the one-time unlocked generation.

The user's form details are retained in that browser during checkout so the research interest does not need to be entered again.

## Free preview

The backend enforces a maximum of 2 ideas when no paid-access credential is supplied. The free preview includes the same structured fields, including:

- title and synopsis
- level-appropriate general and specific objectives
- current research trend or gap
- possible methodology and constructs
- possible data sources
- possible questionnaire or instrument sources
- source records used for grounding

## Paid unlock

One successful payment provides:

- one full Topic Ideas generation
- a selectable set of 5, 8, 10 or 12 ideas
- a maximum of 12 ideas
- a 30-day period in which to use the generation credit
- automatic credit restoration if the paid generation fails before completion

## API behaviour

- `POST /api/topic-ideas` without a payment credential returns a two-idea free preview.
- `POST /api/topic-ideas` with a valid active credential returns the selected paid set, up to 12 ideas, and consumes the one-time credit after success.
- `POST /api/topic-ideas/checkout` creates the Paystack or Stripe checkout.
- `GET /api/topic-ideas/access-plan` reports both the two-idea free preview and the paid maximum of 12.

## Render prices

```env
PROJECTREADY_TOPIC_IDEAS_USD=1.50
PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS=10.00
```
