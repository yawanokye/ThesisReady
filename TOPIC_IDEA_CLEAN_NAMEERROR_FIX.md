# Topic Ideas `_clean` Runtime Fix

## Problem

Topic Ideas generation failed after the strict-resource and DOCX-export update with:

```text
name '_clean' is not defined
```

The result assembly in `app/topic_ideas_service.py` used `_clean(...)` to normalise the research area, context, country or region, methodology and data type, but the helper had not been defined in that module.

## Correction

A local `_clean(value)` helper now normalises whitespace and safely handles missing values before the API response is returned.

A regression test now executes the complete Topic Ideas service path with AI disabled and verifies that all response-summary fields are cleaned without raising a `NameError`.

## Validation

- Python compilation passed
- Topic Ideas targeted tests passed
- Full automated test suite passed: 120 tests
