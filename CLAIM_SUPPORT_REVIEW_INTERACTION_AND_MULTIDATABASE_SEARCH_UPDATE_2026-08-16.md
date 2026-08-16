# Claim Support Review Interaction + Multi-Database Search Update

Date: 2026-08-16

## What changed

### 1. Responsive claim-source search
- Every **Find verified sources** button now shows a visible `Searching…` state immediately.
- The active card shows a spinner and the databases being searched.
- Buttons are re-enabled after success or failure.
- The result status reports how many candidate sources were found and whether any provider was temporarily unavailable.

### 2. Broader scholarly search
ProjectReady now aggregates supported programmatic searches from:
- OpenAlex
- Crossref
- Semantic Scholar
- ERIC
- DataCite
- Europe PMC
- PubMed / NCBI E-utilities
- the project's existing verified evidence bank, including citation-ready student-selected papers

Google Scholar is included as a one-click external search for manual review. The application does not scrape Google Scholar.

Duplicate DOI/title records from multiple indexes are merged. Where a second provider has a better abstract or missing bibliographic field, ProjectReady enriches the merged record and records all databases through which the source was found.

### 3. Responsive source approval
- **Approve as support** now shows `Approving…` while the server validates and stores the approval.
- Results that do not have complete verified bibliographic metadata are clearly labelled **Not citation eligible** instead of presenting an approval button that later fails.
- The candidate card shows the database verification route and accessible evidence where available.

### 4. Placeholder cleanup
A confirmed source approval immediately removes the matching:

`[insert verified source for the unsupported citation removed here]`

marker from the chapter. The citation itself is still inserted only during finalisation so approved 2–3 source groups can be formatted together.

The citation-integrity guard was also corrected so it no longer adds an unsupported-source placeholder after a citation group when every citation in that group is already verified.

### 5. Ignore action
Every unresolved claim or paragraph-density item now has **Ignore**.

Ignore:
- removes the matching source-needed placeholder,
- removes the item from the current review list,
- persists the user's decision across re-audits,
- does not fabricate a source or citation.

### 6. Less noisy claim review
ProjectReady no longer treats ordinary chapter-navigation prose as an external evidence claim. Sentence-level flags are now concentrated on explicit source placeholders and identifiable empirical/factual/relationship claims.

If a substantive paragraph already satisfies the two-source verified minimum, individual uncited sentences are not redundantly listed unless the text itself contains an explicit source-needed marker.

The review therefore concentrates on evidence gaps that remain after normal citation development.

### 7. Final approval citation count
**Finalise approved citations** now reports:
- verified citation references added,
- citation groups added,
- unique verified sources added,
- items ignored by the user,
- unsupported claims remaining,
- paragraph-density gaps remaining,
- paragraph minimum coverage percentage,
- whether final export is unlocked.

### 8. Citation-density directive remains fail-closed
The discipline-and-section citation matrix and the 2–3 verified-source paragraph rule remain active in both:
- Chapter Draft Development
- Chapter Strengthener

ProjectReady is instructed to make a deliberate effort to meet the target while drafting/strengthening. The Claim Support Review lists only gaps that remain.

No source is invented to reach a numerical density target. If suitable verified evidence cannot be found, the gap remains visible or the user may explicitly ignore it.

## Validation
- 191 automated tests pass.
- Python compilation passes.
- Workspace JavaScript syntax validation passes.
- Chapter Strengthener JavaScript syntax validation passes.
- Payment regression tests remain passing.
- Claim approval, Ignore persistence, placeholder cleanup, final citation-count summary and multi-database search tests pass.
