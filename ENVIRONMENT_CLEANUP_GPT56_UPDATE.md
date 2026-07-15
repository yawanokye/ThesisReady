# Environment cleanup and GPT-5.6 routing

This release removes stale production guidance for GPT-5.4, GPT-5.5, GPT-4.1, Stripe test mode, forced Stripe routing, the external humanizer endpoint, and default DeepSeek Topic Ideas routing.

## Recommended model allocation

- GPT-5.6 Luna: low-cost topic ideas, supplementary guidance, diagnostics and general fallback.
- GPT-5.6 Terra: normal chapter drafting, MPhil drafting, chapter strengthening, article drafting and the protected humanizer.
- GPT-5.6 Sol: doctoral drafting and selective high-complexity review or final synthesis.

The application now defaults Topic Ideas to OpenAI. The older DeepSeek-compatible code path remains available only when `PROJECTREADY_TOPIC_IDEA_PROVIDER=deepseek` is explicitly configured.

## Files containing clean production templates

- `.env.production.web.example`
- `.env.production.worker.example`
- `.env.example`
- `.env.projectready-model-router.example`

## Delete these variables from Render

Delete obsolete or conflicting settings rather than leaving them blank:

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_FAST_MODEL
DEEPSEEK_REASONER_MODEL
DEEPSEEK_TOPIC_IDEA_MAX_TOKENS
DEEPSEEK_TOPIC_IDEA_MODEL
DEEPSEEK_TOPIC_IDEA_REASONING_EFFORT
DEEPSEEK_TOPIC_IDEA_THINKING
DEEPSEEK_TOPIC_IDEA_TIMEOUT_SECONDS
HUMANIZER_API_KEY
HUMANIZER_ENABLED
HUMANIZER_ENDPOINT
HUMANIZER_FALLBACK_TO_INTERNAL
HUMANIZER_MODEL
HUMANIZER_REPLACE_INTERNAL
HUMANIZER_TIMEOUT
OPENAI_DRAFT_MODEL
OPENAI_FINAL_MODEL
OPENAI_TIMEOUT_SECONDS
PROJECTREADY_ENABLE_DEEPSEEK
PROJECTREADY_DEFAULT_MODE
PROJECTREADY_EXTRA_AI_PASSES
PROJECTREADY_PREMIUM_REVIEW
PROJECTREADY_DRAFT_TEMPERATURE
PROJECTREADY_REVISION_TEMPERATURE
PROJECTREADY_SMALL_MODEL_STYLE
PROJECTREADY_STYLE_TEXTURE
PROJECTREADY_ALLOW_PARAGRAPH_REORDER
PROJECTREADY_ALLOW_SURFACE_NOISE
PROJECTREADY_AUTO_EXPAND_SHORT_DRAFT
PROJECTREADY_FORCE_STRIPE
PROJECTREADY_STRIPE_MODE
PROJECTREADY_STRIPE_TEST_CHECKOUT_KEY
STRIPE_TEST_SECRET_KEY
STRIPE_TEST_WEBHOOK_SECRET
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
PAYSTACK_PUBLIC_KEY
PAYSTACK_CALLBACK_PATH
PAYSTACK_WEBHOOK_PATH
PROJECTREADY_SQLITE_DB_PATH
PROJECTREADY_SQLITE_PAYMENT_DB
```

Production web and worker services must share the same PostgreSQL `DATABASE_URL`.

## Internal portal security

Do not store the six-digit key in `PROJECTREADY_INTERNAL_ACCESS_KEY` in production. Store only its SHA-256 hash in `PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256`. Because any key shown in logs, screenshots or chat should be treated as exposed, generate a new six-digit key before deploying this release.
