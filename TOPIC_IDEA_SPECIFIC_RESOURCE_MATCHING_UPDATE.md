# Topic Ideas: Idea-Specific Resources, Data Sources and Instruments

## Purpose

Topic Ideas now searches and filters research resources separately for each generated title. It no longer pools constructs from all ideas or attaches general resources merely because they relate to the broad field or country.

## Behaviour

- Builds dataset and instrument queries from each idea's exact title, focal constructs, population and location.
- Searches DataCite first and uses Harvard Dataverse only when DataCite does not return enough topic-specific candidates.
- Searches instrument literature separately for each idea.
- Requires a construct match or multiple non-geographic topic-term matches before displaying a resource.
- Country names alone cannot qualify an official portal.
- Omits unrelated or overly broad datasets, portals, questionnaires and scales.
- Rewrites “Likely data direction” into a topic-specific description of the required data, population and constructs.
- Shows the exact topic scope and matching terms in the user interface.
- Caches duplicate exact queries during the same request to reduce unnecessary metadata calls.

## Recommended environment settings

```env
TOPIC_RESOURCE_SEARCH_TIMEOUT_SECONDS=10
TOPIC_DATASET_RESULTS=6
TOPIC_INSTRUMENT_RESULTS=6
TOPIC_SPECIFIC_RESOURCE_RESULTS=4
TOPIC_DATASET_MIN_RELEVANCE=22
TOPIC_INSTRUMENT_MIN_RELEVANCE=18
```

Raising the two relevance thresholds makes matching stricter. Lowering them increases recall but may allow broader resources.
