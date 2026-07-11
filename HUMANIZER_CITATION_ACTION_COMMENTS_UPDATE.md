# Humanizer, Citation Density and User Action Separation Update

## Purpose

This update responds to working-draft weaknesses where confirmation notes, missing-source prompts and guidance appeared inside the academic narrative. It also strengthens the scholarly humanizer and claim-to-source rules.

## Changes

- All bracketed user instructions are detached from the chapter narrative.
- Actions are consolidated under `USER ACTIONS REQUIRED` and exported in red.
- Each action records the section in which it arose.
- Meta-commentary dominated by placeholders is removed from academic prose.
- Substantive sentences surrounding a removed action are preserved.
- The humanizer now treats drafting commentary as non-academic material.
- Generation and strengthening prompts now require a claim-evidence audit.
- Chapter One citation planning targets are 8-12 relevant citation occurrences per 1,000 words at Masters level and 10-14 at doctoral level.
- Citation targets remain subordinate to relevance and source accuracy. Sources may not be invented or padded.
- Unsupported claims must become a separate user action rather than an embedded comment.

## Files updated

- `app/action_items.py`
- `app/ai_service.py`
- `app/chapter_revision_service.py`
- `app/scholarly_humanizer.py`
- `app/export.py`
- `tests/test_action_items_separation.py`
