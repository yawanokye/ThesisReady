> **Superseded for deep chapter generation:** use `README_CHAPTER_DEPTH_CITATION_UPDATE.md` and the updated environment variables.

# ProjectReady AI – Thesis Quality Fallback Fix

This patch fixes the issue where a draft returned only sparse placeholder text such as:

"This section requires further project-specific detail..."

That output was the local fallback, not a full AI-generated chapter. It appeared when the AI provider did not return a draft, when AI was disabled, or when the request timed out.

## What changed

- The local fallback now creates a more substantive thesis-style draft instead of repeating checklist rules.
- Chapter One fallback now writes developed sections for introduction, background, problem statement, purpose, objectives, questions, significance, delimitations, limitations, and organisation.
- Methodology fallback now includes introduction, philosophy, approach, design, population, sampling, operationalisation, instrument, validity/reliability, ethics, and data analysis tables.
- Literature, Results, Chapter Five and Supplementary Methods fallbacks now provide cleaner thesis-ready structures, tables and precise placeholders.
- The backend now returns a warning if the app used local fallback, so the frontend can tell the user why the output is less developed than the full AI draft.
- Workspace cache-busting has been updated.

## Important

The strongest output still requires a successful AI call and project-specific input. Check these environment variables on Render:

OPENAI_API_KEY
OPENAI_MODEL
OPENAI_FALLBACK_MODEL
OPENAI_TIMEOUT_SECONDS=75
OPENAI_MAX_RETRIES=1
OPENAI_MAX_OUTPUT_TOKENS=6500
PROJECTREADY_EXTRA_AI_PASSES=0
PYTHON_VERSION=3.12.8

If the source in the response is `local_template_fallback`, the AI provider did not generate the chapter.
