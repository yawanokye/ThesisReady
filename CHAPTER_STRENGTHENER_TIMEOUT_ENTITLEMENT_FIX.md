# Chapter Strengthener timeout and entitlement fix

This update prevents a timeout fallback from being treated as a completed paid strengthening.

## Problem fixed

The Chapter Strengthener could return the original chapter with a report such as:

- revision model unavailable
- OpenAI request timed out
- scholarly provider 429 warning

Because the route returned a normal response, a paid revision entitlement could be completed even though no substantive strengthening had occurred.

## Changes

- Increased the default Chapter Strengthener AI timeout from 240 seconds to 900 seconds.
- Reduced the default output ceiling from 30,000 to 18,000 tokens to avoid one oversized request timing out.
- Added model retry support through `PROJECTREADY_CHAPTER_REVISION_MODEL_ATTEMPTS`.
- Added fallback model support through `OPENAI_CHAPTER_REVISION_FALLBACK_MODEL`.
- Cleaned provider-warning formatting so metadata rate limits do not appear as raw Python dictionaries.
- Protected paid users: if the revision service still falls back without rewriting, the protected route now raises an error and the entitlement claim rolls back.

## Render variables to check

```env
PROJECTREADY_CHAPTER_REVISION_USE_AI=1
PROJECTREADY_CHAPTER_REVISION_TIMEOUT_SECONDS=900
PROJECTREADY_CHAPTER_REVISION_MAX_OUTPUT_TOKENS=18000
PROJECTREADY_CHAPTER_REVISION_MODEL_ATTEMPTS=2
OPENAI_CHAPTER_REVISION_MODEL=gpt-5.5
OPENAI_CHAPTER_REVISION_FALLBACK_MODEL=gpt-5.4
OPENAI_CHAPTER_REVISION_DOCTORAL_MODEL=gpt-5.5
```

Use models that your OpenAI account can access. If the primary model is slow or unavailable, the fallback model is tried automatically.
