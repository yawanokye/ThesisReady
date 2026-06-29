# Source relevance gate update

The literature finder now treats the requested result count as a maximum rather than a quota. It attaches fewer sources when the remaining provider records are unrelated.

## Changes

- Uses the user-entered search terms as the focused query without silently appending the full project profile.
- Normalises compound concepts such as `pass-through` so an unrelated title containing only `pass` cannot match.
- Separates substantive topic concepts from locations and common population descriptors.
- Requires a distinctive topic anchor for short compound searches.
- Allows construct-specific papers to remain partly relevant for multi-construct studies.
- Labels every attached record as `highly_relevant` or `partly_relevant` and explains the match.
- Rejects country-only and generic-word matches.
- Skips ERIC for non-education searches.
- Replaces previous automated source-search results after a refined search, while retaining explicitly manual or user-verified sources.
- Removes the previous machine-generated source-note block before writing the refined one.
- Reports how many unrelated records were rejected.

## Example

For `exchange pass-through in Ghana`, papers on exchange-rate pass-through remain eligible. Papers on education, agriculture, health insurance or employee motivation that merely mention Ghana are rejected. A broad paper on exchange-rate regimes that does not discuss pass-through is also rejected.

## Validation

The complete test suite passes, including dedicated tests for country-only false matches, construct-specific literature and focused user-entered queries.
