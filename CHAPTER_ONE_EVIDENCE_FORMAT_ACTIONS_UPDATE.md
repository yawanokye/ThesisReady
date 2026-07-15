# Chapter One evidence, format and action-item update

This release addresses weaknesses observed in a Bachelor-level Chapter One draft while applying the same controls across Bachelors, non-research Masters, research Masters/MPhil, professional doctorate and PhD work.

## Improvements

### Fewer unnecessary action items

- The drafting prompt now completes every element that can be derived from the title, objectives, selected design, project profile and evidence bank.
- An `ACTION REQUIRED` item is reserved for material information that only the user, supervisor or institution can supply.
- Repeated requests for the same population, location, period, sample, instrument, ethics information or chapter structure are collapsed at the first relevant location.
- Generic requests to confirm generated objective, purpose or title wording are removed.
- Broken phrases caused by absent values, such as `among in, Ghana`, are prohibited.

### Automatic source support

- When the attached source bank is too small, the app can automatically search the existing scholarly metadata providers before drafting.
- The search is level- and chapter-sensitive and remains relevance-gated.
- Retrieved records are candidates only. The model may cite a record only when it directly supports the claim.
- Automatic source support can be disabled for an individual project.

### Stronger citation-density planning

Citation-occurrence planning ranges were raised for all academic levels and for both the Thesis Workspace and Chapter Strengthener. Accuracy and relevance remain mandatory, so the app does not insert decorative or invented citations.

### School-specific Chapter One formats

The Thesis Workspace and Chapter Strengthener now include controls for:

- continuous Background to the Study without internal subheadings;
- thematic background with lower-level subheadings;
- school-guideline-driven background format;
- concise Purpose of the Study aligned with the general objective;
- concise purpose paragraph;
- expanded purpose with a brief rationale;
- expected number of chapters.

The Organisation of the Study now uses the configured chapter count rather than asking whether the work has five or seven chapters.

## New environment variables

```env
PROJECTREADY_AUTO_SOURCE_SUPPORT=1
PROJECTREADY_AUTO_SOURCE_QUERY_COUNT=2
PROJECTREADY_AUTO_SOURCE_RESULTS_PER_QUERY=14
PROJECTREADY_AUTO_SOURCE_MINIMUM_OVERRIDE=0
```

## Validation

- Python compilation passed.
- JavaScript syntax checks passed.
- 115 automated tests passed.
