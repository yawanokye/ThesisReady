# ProjectReady AI topic ideas page patch

This patch adds an interactive page where users can generate thesis/dissertation title ideas, brief synopses and proposed research objectives based on current literature-search metadata.

## New page

- `/topic-ideas`
- `/ideas` as an alias

## New API endpoint

- `POST /api/topic-ideas`

The endpoint accepts research area, context, country/region, level, methodology, keywords and trend focus. It searches the existing source-finder metadata providers, removes detected retracted or withdrawn records, and then produces researchable thesis/dissertation titles with brief synopses and objectives matched to the selected academic level.

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
- one proposed general objective for each idea
- level-appropriate specific objectives: 4 for Bachelors, 4 for Non-Research Masters, 5 for Research Masters/MPhil, 5 for Professional Doctorate and 6 for PhD
- a short explanation of how the objectives align with the selected level
- current research trend or gap
- possible methodology
- possible variables or constructs
- possible data sources
- potential contribution
- evidence source keys
- attention note for supervisor/data-access confirmation
- source records used for trend grounding

## Academic-level objective design

Every returned idea now includes a `proposed_objectives` object with:

- `general_objective`
- `specific_objectives`
- `level_alignment`

The AI prompt requests objectives aligned with the title, variables, methodology and likely data. A backend normalisation layer guarantees that every idea still receives the required number of objectives if an AI response omits or under-produces them. Existing topic outputs remain unchanged and the objectives are added to the web display and copied text.

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
