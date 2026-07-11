# Proximate Action Items and Natural Scholarly Humanizer Update

## Purpose

This update addresses two related output-quality problems:

1. user actions were collected at the bottom of a chapter, far from the sentence or paragraph requiring attention; and
2. the humanizer needed stronger control of repetitive, formulaic and over-polished academic prose without changing evidence or reducing long-chapter depth.

## Proximate red action items

- Every missing-source, confirmation, evidence or author instruction is removed from the thesis sentence.
- The complete action is placed on its own bracketed line immediately after the affected paragraph, list or action-only location.
- Actions are numbered successively from 1 in their order of appearance.
- Duplicate actions are retained only at their first relevant location.
- The existing DOCX exporter colours the complete bracketed instruction red.
- New prompts instruct the writing and strengthening models not to collect actions in a bottom appendix.

Example:

```text
The curriculum establishes the expected grammar-learning outcomes.

[ACTION REQUIRED 1: Insert the verified Ghana SHS English curriculum source.]
```

## Natural scholarly humanizer

The protected humanizer now checks and improves:

- repeated sentence and paragraph openings;
- repeated use of `the study`, `this chapter` and generic framing;
- mechanical connectors such as repeated `furthermore` and `moreover`;
- overlong or overloaded sentences;
- uniform sentence and paragraph rhythm;
- filler phrases and unnecessary meta-commentary;
- excessive nominalisation where a clear verb is more natural;
- predictable paragraph endings and formulaic source presentation;
- author-by-author literature listing where synthesis is more appropriate.

It does not add deliberate errors or artificial drafting noise.

## Long-chapter refinement

Long chapters are no longer skipped by the model humanizer or rewritten as one block.

- The chapter is split into heading-led batches of about 2,400 words.
- Balanced mode refines only weak batches, capped at four by default.
- Deep mode processes all eligible batches, capped at twelve by default.
- References, source-use audits and appendices are protected from model rewriting.
- Every batch is checked for preservation before it is accepted.

## Preservation gate

A humanized version is rejected when it changes protected material, including:

- headings and numbered section titles;
- numbered objectives and research questions;
- years, statistics and numerical values;
- author-date citation blocks;
- URLs and DOI strings;
- bracketed action items;
- display equations;
- Markdown table rows;
- word count beyond the permitted style-only range.

## Recommended environment settings

```env
PROJECTREADY_HUMANIZER_MODE=balanced
PROJECTREADY_HUMANIZER_MODEL_THRESHOLD=94
PROJECTREADY_HUMANIZER_BATCH_WORDS=2400
PROJECTREADY_HUMANIZER_MAX_BATCHES_BALANCED=4
PROJECTREADY_HUMANIZER_MAX_BATCHES_DEEP=12
```

Use `balanced` for normal paid work. Use `deep` when the user explicitly wants the strongest section-by-section style refinement and accepts the additional model cost.

## Files amended

- `app/action_items.py`
- `app/scholarly_humanizer.py`
- `app/ai_service.py`
- `app/chapter_revision_service.py`
- `app/static/workspace.html`
- `app/static/chapter_strengthener.html`
- `.env.example`
- `.env.projectready-model-router.example`
- `tests/test_action_items_separation.py`
- `tests/test_scholarly_humanizer.py`
- `PROXIMATE_ACTIONS_NATURAL_HUMANIZER_UPDATE.md`
