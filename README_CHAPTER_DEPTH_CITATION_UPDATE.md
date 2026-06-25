# ThesisReady chapter depth and citation-density update

This update aligns the five standard chapters with the approved page ranges for each academic level. Page ranges are converted into word-planning targets using an estimated 330 words per formatted page. Final DOCX pagination will still vary with tables, equations, figures, headings and references.

## Page targets built into the app

| Chapter | Bachelor | Non-Research Master's | Research Master's/MPhil | Professional Doctorate | PhD |
|---|---:|---:|---:|---:|---:|
| 1. Introduction | 10–15 | 10–15 | 15–20 | 15–22 | 25–35 |
| 2. Literature Review | 15–22 | 20–30 | 35–45 | 40–60 | 60–80 |
| 3. Methodology | 10–15 | 12–18 | 15–22 | 25–35 | 30–45 |
| 4. Results and Discussion | 20–25 | 20–30 | 20–32 | 35–45 | 60–80 |
| 5. Summary, Conclusions and Recommendations | 8–12 | 8–15 | 8–12 | 10–15 | 20–30 |

## What changed

- Added level-by-chapter page, word and citation-density targets.
- Added section-level word budgets so depth is distributed across the selected headings.
- Added chunked generation for long MPhil and doctoral chapters. This prevents a 40–80 page target from being compressed into one short response.
- Added an evidence-safe expansion pass when a shorter chapter is materially below its minimum target.
- Increased the source finder default to 30 records and its maximum to 60 records per search.
- Increased the accumulated source bank and prompt source capacity to 100 records.
- Increased citation-density guidance by chapter and level, while retaining relevance checks and placeholders where evidence is missing.
- Added generation metrics to the API and workspace, including estimated pages, word count, citation occurrences per 1,000 words and whether the minimum depth target was reached.
- Prevented long whole-chapter revision passes from compressing high-depth outputs.

## Recommended Render environment variables

```text
OPENAI_MAX_OUTPUT_TOKENS=32000
OPENAI_MAX_OUTPUT_TOKENS_HARD_CAP=64000
OPENAI_SAFE_RETRY_MAX_OUTPUT_TOKENS=12000
PROJECTREADY_WORDS_PER_PAGE=330
PROJECTREADY_CHUNKED_GENERATION_THRESHOLD_WORDS=9000
PROJECTREADY_CHUNK_TARGET_WORDS=8000
PROJECTREADY_MAX_CHAPTER_CHUNKS=4
PROJECTREADY_DEPTH_ACCEPTANCE_RATIO=0.90
PROJECTREADY_LONG_CHAPTER_REVISION_LIMIT_WORDS=12000
```

`OPENAI_MAX_OUTPUT_TOKENS` is treated as the per-call cap. Long chapters are divided into contiguous section chunks when the chapter target exceeds the chunking threshold.

## Important operating rule

The app will not fabricate citations, findings or statistics merely to meet a page or citation target. Where the evidence bank is insufficient, the draft should insert a precise bracketed placeholder and the workspace will report that the chapter remains below its planned depth.

## Main files changed

- `app/ai_service.py`
- `app/source_finder.py`
- `app/schemas.py`
- `app/routers/generation.py`
- `app/routers/sources.py`
- `app/static/app.js`
- `app/static/workspace.html`
- `.env.example`
- `.env.projectready-model-router.example`
