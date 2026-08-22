# ProjectReady API Cost-Control Update — 22 Aug 2026

This update targets long chapter drafting and Chapter Strengthener API spend without reducing the 50-paper selected literature library.

## What changed

- All 50 selected papers remain available to the project evidence map; section calls carry only the most relevant original passages.
- Long Chapter Two/other long-chapter planning is local by default. The optional AI planner is off unless `PROJECTREADY_LONG_CHAPTER_AI_PLAN=1`.
- Chunked chapters no longer trigger a second whole-chapter depth rewrite. Short chunks receive append-only continuation text so already-paid output is preserved.
- Model-based scholarly humanisation is off by default. The protected deterministic/local humaniser remains active. Set `PROJECTREADY_ENABLE_MODEL_HUMANIZER=1` only when deliberately paying for an extra style pass.
- Background full-job retries are off unless `PROJECTREADY_ALLOW_JOB_RETRIES=1`.
- Same-model retries are off unless `PROJECTREADY_SAFE_MODEL_RETRY=1`.
- Cross-model fallback is off unless `PROJECTREADY_ALLOW_FALLBACK_MODEL=1`, preventing a stale fallback (including Sol) from silently running after a failed Terra request.
- Chapter Strengthener fallback models/retries are likewise opt-in.
- GPT-5.6 reasoning effort defaults to `low` for substantive drafting and `none` for optional style/planning work, reducing invisible billed reasoning tokens.
- Requests explicitly use `service_tier=default` unless the developer overrides it, so a project/account Fast/Priority setting cannot silently double token prices.
- Repeated long-chapter calls use a stable prompt-cache key and a more stable prompt prefix to improve cached-input reuse.
- Each completed background job now stores `ai_usage` with completed API call count, input tokens, cached input tokens, output tokens, reasoning tokens, and locally estimated USD cost.
- The restricted developer portal adds an **AI usage** column for completed jobs. Failed provider attempts are logged because a timeout can still be billable even when usage metadata is not returned to the application.

## Recommended production values

```env
PROJECTREADY_OPENAI_SERVICE_TIER=default
PROJECTREADY_OPENAI_REASONING_EFFORT=low
PROJECTREADY_ALLOW_FALLBACK_MODEL=0
PROJECTREADY_SAFE_MODEL_RETRY=0
PROJECTREADY_ALLOW_JOB_RETRIES=0
PROJECTREADY_RETRY_MODEL_TIMEOUT_JOBS=0
PROJECTREADY_LONG_CHAPTER_AI_PLAN=0
PROJECTREADY_ENABLE_MODEL_HUMANIZER=0
PROJECTREADY_CHUNK_TARGET_WORDS=3000
PROJECTREADY_MAX_CHAPTER_CHUNKS=10
PROJECTREADY_MAX_CHUNK_CONTINUATIONS=8
PROJECTREADY_ALLOW_CHAPTER_REVISION_RETRIES=0
PROJECTREADY_ALLOW_CHAPTER_REVISION_FALLBACK_MODELS=0
PROJECTREADY_CHAPTER_REVISION_MODEL_ATTEMPTS=1
```

`OPENAI_FALLBACK_MODEL` may be left blank in production. If it is configured, it still cannot run unless `PROJECTREADY_ALLOW_FALLBACK_MODEL=1`.

## Important interpretation of failed calls

A request that times out at the application boundary may have already consumed provider tokens. The application therefore logs failed model attempts separately and never treats an unknown failed-call cost as zero. Exact provider billing remains authoritative in the OpenAI usage dashboard.

## Validation

- 216 automated tests passed.
- Python compilation passed.
- Thesis Workspace JavaScript syntax passed.
- Chapter Strengthener JavaScript syntax passed.
- Restricted developer portal JavaScript syntax passed.
