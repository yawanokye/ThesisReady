# Chapter citation, objectives and reference-list update

This update applies to Thesis Workspace chapter generation and the Chapter Strengthener at every academic level.

## Changes

- Increased level- and chapter-specific in-text citation planning ranges.
- Increased automatic source-support minimums and default search breadth.
- Added paragraph-level evidence rules for Chapter One and Chapter Two.
- Kept Purpose of the Study concise by default.
- Removed explanatory commentary, level-alignment notes and methodological commentary after research objectives and research questions.
- Restarted specific-objective and research-question numbering independently at 1.
- Added post-generation correction for questions accidentally written on one line.
- Cleaned chapter reference lists by removing bullets, numbering, duplicates, source keys, relevance labels and source-audit tables.
- Alphabetised reference entries and retained only one References section.
- Removed Source Use Audit as a chapter-output and compliance requirement. Source-selection diagnostics remain internal to the application workflow.

## Updated citation planning ranges per 1,000 substantive words

| Level | Chapter One | Chapter Two | Chapter Three | Chapter Four | Chapter Five |
|---|---:|---:|---:|---:|---:|
| Bachelors | 12-16 | 16-22 | 6-9 | 6-10 | 4-7 |
| Non-research Masters | 13-18 | 18-24 | 7-10 | 7-11 | 5-8 |
| Research Masters/MPhil | 15-20 | 20-28 | 8-12 | 8-13 | 6-9 |
| Professional Doctorate | 16-22 | 22-30 | 9-13 | 9-14 | 7-10 |
| PhD | 18-24 | 24-32 | 10-15 | 10-16 | 8-12 |

The ranges guide density. They do not permit fabricated, decorative or irrelevant citations.

## Recommended production values

```env
PROJECTREADY_AUTO_SOURCE_SUPPORT=1
PROJECTREADY_AUTO_SOURCE_QUERY_COUNT=3
PROJECTREADY_AUTO_SOURCE_RESULTS_PER_QUERY=18
```

Apply the same values to the web service and background worker when the variables are explicitly set in Render.
