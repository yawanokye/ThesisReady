# ProjectReady AI safe human-quality timeout fix

This patch fixes the recent long `/draft` request/internal-error behaviour and keeps the writing quality high without corrupting the academic text.

## Main changes

- Keeps OpenAI calls bounded with `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`, and `OPENAI_MAX_OUTPUT_TOKENS`.
- Keeps expensive multi-pass AI revision disabled by default with `PROJECTREADY_EXTRA_AI_PASSES=0`.
- Removes risky post-processing behaviour from the active generation path. The app no longer adds deliberate typos, spacing errors, false starts, fabricated citation clusters, or secondary Groq rewrites.
- Keeps a controlled high-burstiness academic style inside the main prompt: varied sentence length, varied paragraph shape, stronger interpretation, context-specific transitions, and cautious scholarly judgement.
- Preserves APA references, source-use audit, supplementary methods chapter, equation instructions, and clean Results chapter guidance.

## Render environment variables

Recommended:

```text
OPENAI_TIMEOUT_SECONDS=75
OPENAI_MAX_RETRIES=1
OPENAI_MAX_OUTPUT_TOKENS=6500
PROJECTREADY_EXTRA_AI_PASSES=0
PYTHON_VERSION=3.12.8
```

Use clear build cache and deploy after pushing.
