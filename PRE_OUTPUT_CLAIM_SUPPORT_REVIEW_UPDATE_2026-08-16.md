# ProjectReady Pre-Output Claim Support Review Update — 16 August 2026

## Scope

This update applies the same verified citation-density and claim-support policy to both:

- Thesis Workspace / Chapter Draft Development
- Chapter Strengthener

The payment reliability changes from the complete Payment + Citation Quality Upgrade are retained.

## Pre-output evidence gate

After a chapter is generated or strengthened, ProjectReady now runs a sentence-level and paragraph-level evidence audit before final chapter export.

Evidence-bearing claims that do not have an in-text citation are highlighted in red in a claim-support preview. Paragraphs below the verified-source density floor are listed separately.

The default evidence-led paragraph policy is:

- minimum: 2 distinct verified sources where scholarly support is required
- preferred: 3 distinct verified sources where suitable evidence exists

The discipline/section citation-density matrix remains active as the broader references-per-1,000-words target. The paragraph rule and the matrix operate together.

Citation-light sections such as objectives, research questions, standalone hypotheses, project-specific procedures, pure results statements, and finding-led recommendations are not padded with unnecessary citations.

## Find, review and approve sources

For each highlighted claim or paragraph evidence gap, the user can choose **Find verified sources**.

ProjectReady searches its configured scholarly source providers and displays candidate source metadata and accessible evidence excerpts. Search results are never inserted automatically.

The user must approve a source for the specific claim before it is eligible for insertion.

If accessible abstract/full-text evidence is available, the user confirms that the evidence supports the claim. If only bibliographic metadata is available, the user must open/review the source text and explicitly confirm that it supports the claim before approval.

Up to three approved relevant sources can be attached to a claim or paragraph support item.

## Anti-hallucination controls

The density target can never override source integrity.

A citation counts toward the paragraph target only when it maps to a verified source fingerprint in ProjectReady's source bank, selected-paper library, retrieved literature, or user-confirmed bibliographic record.

ProjectReady must not:

- invent an author, title, year, journal, DOI, URL, volume, issue or page number
- infer detailed findings from a title or metadata-only record
- cite an unverified source merely to reach 2–3 citations per paragraph
- silently approve a search result
- fabricate a statistical result

When sufficient verified evidence is unavailable, the claim remains highlighted and the export remains locked. The user can search again, upload/confirm a selected paper, revise the claim, or remove an unsupported assertion.

## Applying approved citations

For author-date styles, approved citations are inserted deterministically from the verified bibliographic metadata. The ordinary citation-integrity gate then runs again and the reference list is rebuilt from allowed sources.

For numeric styles such as IEEE or Vancouver, approvals are retained for the final numbering pass rather than inserting numbers that could corrupt existing citation order.

After citations are applied, ProjectReady reruns the full claim-support and paragraph-density audit. Export unlocks only when the chapter is ready.

## Export gate and existing projects

The server now enforces the evidence gate for chapter DOCX export, strengthened chapter export, and compilation of the full project working file.

Projects created before this update are handled safely. If a saved chapter has no stored claim-support review, ProjectReady creates the review automatically on the first export attempt. A citation-light chapter can proceed. A chapter with unresolved evidence claims is stopped and the user is directed to Claim Support Review.

## Student-selected papers

The existing My Selected Papers library remains available for up to 50 student-selected papers. Verified or user-confirmed selected papers can be used alongside ProjectReady-discovered literature during claim support review.

## Payment reliability retained

Normal production checkout remains separated from private Stripe test checkout. Stripe test checkout requires the explicit test-enable switch, preventing stale test variables from sending live users to the private test-key screen.
