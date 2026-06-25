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

## Data-source and instrument discovery update

The topic-idea workflow now runs a second resource-discovery stage after variables and constructs have been identified.

For secondary-data, econometric, time-series and panel-data directions, each idea now includes candidate data sources matched to the proposed constructs. The resource finder searches:

- DataCite dataset DOI metadata
- published datasets in Harvard Dataverse
- a locally maintained catalogue of official data portals, including appropriate national and international statistical sources

For survey, qualitative, mixed-method and other primary-data directions, each idea now includes candidate publications that may contain a questionnaire, scale, index, interview guide, protocol, checklist or other instrument that could be adopted or adapted. These candidates are retrieved through the existing OpenAlex, Crossref, Semantic Scholar and ERIC searches.

The output always labels the records as candidates. Users are instructed to inspect the original source and confirm:

- variable and construct coverage
- population and contextual fit
- reliability and validity
- scoring and coding
- translation and cultural adaptation
- licence or copyright permission
- ethical and institutional requirements

The application does not invent named datasets or instruments when a live search is unavailable.

Optional resource-search environment variables:

```text
TOPIC_RESOURCE_SEARCH_TIMEOUT_SECONDS=10
TOPIC_DATASET_RESULTS=8
TOPIC_INSTRUMENT_RESULTS=8
```
