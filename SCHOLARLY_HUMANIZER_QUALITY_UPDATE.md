# Protected Scholarly Humanizer Update

## Purpose

The humanizer remains part of ProjectReady AI, but it now improves natural scholarly quality without inserting artificial mistakes, stock phrases, rare synonyms or unsupported content.

## Main changes

- Added `app/scholarly_humanizer.py` as the shared humanizer for the Thesis Workspace and Chapter Strengthener.
- Removed random sentence changes and mechanical synonym replacement.
- Removed legacy phrases such as `That matters`, `This qualification matters...`, excessive `insofar as`, `the present investigation`, and `non-trivial function`.
- Added a deterministic style diagnostic for generic language, repeated openings, repeated connectors, sentence-length problems and paragraph uniformity.
- Added preservation gates for headings, years, statistics, citations, URLs, references and bracketed action placeholders.
- Protected tables, equations, numbered objectives/questions, lists, headings, references and Source Use Audits from local rewriting.
- Added four user-selectable modes:
  - `Light`: local protected refinement only.
  - `Balanced`: local refinement plus one model pass only when the diagnostic or supplied writing direction requires it.
  - `Deep`: one preservation-gated model pass after local refinement.
  - `Off`: no humanizer.
- Long chapters are humanized section by section rather than rewritten as one whole document.
- Chapter Strengthener now applies the same protected humanizer after substantive revision.
- Removed backend Python copies from `app/static` so an obsolete humanizer is not publicly served.

## Environment settings

```env
PROJECTREADY_HUMANIZER_MODE=balanced
PROJECTREADY_HUMANIZER_MODEL_THRESHOLD=86
PROJECTREADY_ENABLE_GROQ_HUMANIZER=0
```

For long doctoral chapters:

```env
PROJECTREADY_CHUNKED_GENERATION_THRESHOLD_WORDS=4500
PROJECTREADY_CHUNK_TARGET_WORDS=2200
PROJECTREADY_MAX_CHAPTER_CHUNKS=16
```

## Cost and quality balance

Balanced mode is recommended. It always runs the no-cost protected local pass, then uses a paid model revision only when the style score remains below the configured threshold or the user supplied a writing sample, supervisor direction or preferred style. Long chapters avoid a second whole-document rewrite.

## Validation

The update includes tests for preservation of citations, numbers, placeholders and references, removal of legacy artefacts, availability of humanizer controls in both workspaces, and exclusion of backend Python files from the public static directory.
