# ProjectReady AI Journal Article Page Patch

This patch adds a separate page for drafting journal-article-ready manuscripts from study details, journal guidelines, source notes and results.

## New routes

- `/journal-article`
- `/article`
- `POST /api/journal-article/draft`
- `POST /api/journal-article/export`

## New/updated files

- `app/main.py`
- `app/routers/journal_article.py`
- `app/journal_article_service.py`
- `app/static/journal_article.html`
- `app/static/journal_article.css`
- `app/static/journal_article.js`
- `app/static/index.html`
- `app/static/topic_ideas.html`
- `app/static/workspace.html`
- compatibility copies: `journal_article.html`, `static/journal_article.css`, `static/journal_article.js`, `topic_ideas.html`, `workspace.html`

## What the page collects

- Working article title/topic
- Research area
- Target journal/publisher
- Journal author guidelines, aims and scope
- Article type
- Academic level
- Methodology/design
- Word limit and citation style
- Study context
- Research problem/gap
- Objectives/questions/hypotheses
- Theory/conceptual framework
- Variables/constructs/themes
- Data, analysis output or results summary
- Key findings and contribution
- Verified reference/DOI/source notes

## Draft output

The page returns a Markdown journal article draft with:

- Title
- Abstract
- Keywords
- Introduction
- Literature/theory or conceptual section
- Methods
- Results or findings
- Discussion
- Conclusion
- Declarations
- References
- Article readiness checklist

The structure is adapted to article type and pasted journal guidelines. If information is missing, the draft uses bracketed attention placeholders such as `[confirm sample size]`, `[insert results table]`, or `[verify ethics approval]`.

## Source and retraction safeguards

The page can run the existing source finder before drafting. It locally excludes detected records whose metadata indicates:

- retracted
- withdrawn
- removed article
- retraction notice
- expression of concern

Those records are not used in the article body, citations, tables or reference list where detectable in metadata.

## Model routing

Default routing is level-based:

- Bachelor: `OPENAI_ARTICLE_BACHELOR_MODEL`, default `gpt-5.4`
- Non-Research Masters: `OPENAI_ARTICLE_MASTERS_MODEL`, default `gpt-5.4`
- Research Masters/MPhil or review/conceptual article: `OPENAI_ARTICLE_RESEARCH_MODEL`, default `gpt-5.5`
- PhD/DBA/Professional Doctorate: `OPENAI_ARTICLE_DOCTORAL_MODEL`, default `gpt-5.5`

## Recommended environment variables

```text
PROJECTREADY_ARTICLE_USE_AI=1
PROJECTREADY_ARTICLE_SOURCE_LIMIT=24
OPENAI_ARTICLE_BACHELOR_MODEL=gpt-5.4
OPENAI_ARTICLE_MASTERS_MODEL=gpt-5.4
OPENAI_ARTICLE_RESEARCH_MODEL=gpt-5.5
OPENAI_ARTICLE_DOCTORAL_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-5.4-mini
```

No new Python package dependency is required. The DOCX export uses `python-docx`, which is already part of the existing ProjectReady AI dependency set.

## Deployment

```bash
git add app/main.py app/routers/journal_article.py app/journal_article_service.py app/static/journal_article.html app/static/journal_article.css app/static/journal_article.js app/static/index.html app/static/topic_ideas.html app/static/workspace.html
git commit -m "Add journal article drafting page"
git push
```

Then on Render:

```text
Manual Deploy -> Clear build cache & deploy
```

Test after deploy:

```text
https://your-domain.com/journal-article
```
