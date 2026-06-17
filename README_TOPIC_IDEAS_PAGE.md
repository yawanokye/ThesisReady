# ProjectReady AI topic ideas page patch

This patch adds a new interactive page where users can generate thesis/dissertation title ideas and brief synopses based on current literature-search metadata.

## New page

- `/topic-ideas`
- `/ideas` as an alias

## New API endpoint

- `POST /api/topic-ideas`

The endpoint accepts research area, context, country/region, level, methodology, keywords and trend focus. It searches the existing source-finder metadata providers, removes detected retracted or withdrawn records, and then produces researchable thesis/dissertation titles with brief synopses.

## Files added/updated

- `app/main.py`
- `app/routers/topic_ideas.py`
- `app/topic_ideas_service.py`
- `app/static/topic_ideas.html`
- `app/static/topic_ideas.css`
- `app/static/topic_ideas.js`
- `app/static/workspace.html`
- `app/static/index.html`
- `workspace.html` and `static/*` copies for projects that keep static files at repository root

## Behaviour

The page returns:

- thesis/dissertation title ideas
- brief synopsis for each title
- current research trend or gap
- possible methodology
- possible variables or constructs
- possible data sources
- potential contribution
- evidence source keys
- attention note for supervisor/data-access confirmation
- source records used for trend grounding

## Retraction protection

The topic-idea generator includes a local retraction guard. It excludes records where metadata or title/abstract/status contains indicators such as:

- retracted
- retraction notice
- withdrawn
- removed article
- expression of concern

This is an additional guard and does not replace final source verification.

## Environment variables

Recommended optional settings:

```text
PROJECTREADY_TOPIC_IDEAS_USE_AI=1
OPENAI_TOPIC_IDEA_MODEL=gpt-5.4
OPENAI_TOPIC_IDEA_RESEARCH_MODEL=gpt-5.5
OPENAI_TOPIC_IDEA_DOCTORAL_MODEL=gpt-5.5
```

The page uses the existing `OPENAI_API_KEY`. It does not add any new package dependency.

## Deploy

```bash
git add app/main.py app/routers/topic_ideas.py app/topic_ideas_service.py app/static/topic_ideas.html app/static/topic_ideas.css app/static/topic_ideas.js app/static/workspace.html app/static/index.html
git commit -m "Add thesis topic ideas page"
git push
```

Then on Render use **Manual Deploy → Clear build cache & deploy**.
