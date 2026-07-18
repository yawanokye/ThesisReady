# All-module new-job clearing and expanded trend grounding

## New-job clearing

Topic Ideas, Thesis Workspace and Chapter Strengthener now provide a clear-and-start-new-job action. The action removes job-specific browser state, output, uploaded-file references and current-project restoration data while retaining payment credentials and registration profile data. A one-time `new_job=1` reload marker forces the Workspace and Strengthener forms to initialise cleanly even when the browser attempts to restore previous form entries.

## Topic Ideas trend grounding

Topic Ideas now uses up to 24 strongly relevant literature records by default and may search up to 36 records before relevance filtering. The limits are configurable with:

```env
PROJECTREADY_TOPIC_TREND_SOURCE_LIMIT=24
PROJECTREADY_TOPIC_TREND_SEARCH_LIMIT=36
```

The application does not pad the source list with weak or unrelated records when fewer sources pass the relevance gate.
