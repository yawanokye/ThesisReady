# Topic Ideas: level-appropriate objectives update

Each generated topic idea now retains all existing output and additionally includes:

- one proposed general objective;
- four specific objectives for Bachelors;
- four specific objectives for Non-Research Masters;
- five specific objectives for Research Masters/MPhil;
- five specific objectives for Professional Doctorate/DBA/DEd;
- six specific objectives for PhD; and
- a level-alignment note explaining the intended depth.

## Updated files

- `app/topic_ideas_service.py`
- `app/static/topic_ideas.js`
- `app/static/topic_ideas.html`
- `app/static/topic_ideas.css`
- `README_TOPIC_IDEAS_PAGE.md`

## Added files

- `tests/test_topic_idea_objectives.py`
- `TOPIC_IDEAS_LEVEL_OBJECTIVES_UPDATE.md`

The backend validates and completes objectives even when an AI response omits some items. The frontend shows the objectives inside each topic card and includes them when the user copies the results.
