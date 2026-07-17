# Topic Ideas strict resources and DOCX export update

## Resource filtering

- Secondary-dataset discovery is now opt-in. It runs only when the user selects a secondary-data, econometric, time-series, panel-data or combined primary/secondary design.
- A primary survey with `Data access: Not sure` no longer triggers DataCite or Harvard Dataverse searches.
- Generic matches such as `employee`, `development`, `performance`, `training`, `service` or `Ghana` cannot qualify a dataset by themselves.
- A dataset must match a meaningful multiword construct, together with a specific topic or contextual anchor, or satisfy a stronger multi-term/context gate.
- Default dataset relevance increased from 5 to 22. Default instrument relevance increased from 14 to 18.
- If no defensible candidate is found, the dataset or instrument section is omitted rather than filled with an unrelated record.
- The Topic Ideas page displays only non-empty, strongly matched resource groups.

## DOCX export

- Added `POST /api/topic-ideas/export-docx`.
- Added an `Export DOCX` button beside `Copy results`.
- The export includes generation metadata, trend summary, titles, synopses, objectives, methodology, constructs, topic-specific data direction, strongly matched resources, contributions and literature records.
- The DOCX contains editable text and clickable source links.

## Environment defaults

```env
TOPIC_DATASET_MIN_RELEVANCE=22
TOPIC_INSTRUMENT_MIN_RELEVANCE=18
```
