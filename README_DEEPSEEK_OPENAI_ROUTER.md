# ProjectReady AI: DeepSeek + OpenAI Model Router Patch

This patch updates `app/ai_service.py` so ProjectReady AI can combine DeepSeek and OpenAI models to reduce cost while protecting thesis-writing quality.

## Recommended Render environment variables

```env
PROJECTREADY_ENABLE_DEEPSEEK=1
PROJECTREADY_DEFAULT_MODE=standard
PROJECTREADY_EXTRA_AI_PASSES=0
PROJECTREADY_PREMIUM_REVIEW=0

DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_FAST_MODEL=deepseek-chat
DEEPSEEK_REASONER_MODEL=deepseek-reasoner

OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4.1
OPENAI_DRAFT_MODEL=gpt-4.1
OPENAI_FINAL_MODEL=gpt-4.1
OPENAI_REVIEW_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-4.1-mini

OPENAI_TIMEOUT_SECONDS=90
OPENAI_MAX_OUTPUT_TOKENS=32000
PROJECTREADY_PLAN_MAX_TOKENS=2500
PROJECTREADY_REVIEW_MAX_TOKENS=2500
```

## Modes

- `economy`: DeepSeek plan + DeepSeek draft; OpenAI fallback only if DeepSeek fails.
- `standard`: DeepSeek source/argument plan + GPT-4.1 full chapter draft. Recommended default.
- `enhanced`: DeepSeek stronger plan + GPT-4.1 draft. Can enable review with extra pass.
- `premium`: DeepSeek plan + GPT-4.1 draft + optional GPT-5.5 compact review + GPT-4.1 final revision when `PROJECTREADY_EXTRA_AI_PASSES=1`.

## What changed

1. Added a DeepSeek client using the OpenAI-compatible SDK.
2. Added stage-based model routing: plan, draft, review and final.
3. Uses DeepSeek for cheaper source mapping and chapter planning.
4. Uses GPT-4.1 for full thesis-standard chapter drafting in standard mode.
5. Uses GPT-5.5 only for optional compact review, not long chapter generation.
6. Keeps a safe local fallback if all providers fail.
7. Stops running artificial text-noise, fake citation clustering, paragraph randomisation and detector-oriented post-processing.
8. Strengthens instructions for source-bank use, in-text citations, APA references and Source Use Audit.

## Deployment

Replace:

```text
app/ai_service.py
```

Then run:

```bash
git add app/ai_service.py
git commit -m "Add DeepSeek and OpenAI cost-aware model routing"
git push
```

On Render use: **Manual Deploy → Clear build cache & deploy**.
