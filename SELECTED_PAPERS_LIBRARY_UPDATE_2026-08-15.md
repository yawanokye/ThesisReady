# ProjectReady Selected Papers Library Upgrade

## What changed

ProjectReady now supports a student-curated paper library alongside automatic scholarly source discovery.

### Thesis Workspace

- Students can upload up to 50 selected papers per project.
- Supported paper formats: PDF, DOCX, TXT, MD and RTF.
- Selected papers remain separate from ProjectReady's automatic literature finder in the user interface.
- Relevant selected papers are carried across all chapters and can support background, literature review, theory, methodology, discussion, conclusions and other evidence-led sections.
- ProjectReady ranks a compact subset of the uploaded papers for the active chapter rather than sending all fifty complete papers to the model on every call.
- Extracted evidence covers the front of the paper plus method, results/findings, discussion and conclusion windows where these sections can be identified.

### Chapter Strengthener

- The same optional selected-paper library is available inside Literature Support.
- Papers can be attached before a new revision-only project is created.
- Existing ProjectReady projects automatically reuse papers already saved with the project.
- Newly attached Strengthener papers can be saved into the project after a successful strengthening request.

## Citation integrity rules

Uploading a paper does not automatically authorise ProjectReady to invent or guess its citation metadata.

- When a DOI is present and its bibliographic record can be verified, the paper becomes citation-ready automatically.
- If metadata cannot be verified, the paper remains evidence-only until the student confirms title, author(s) and publication year.
- Evidence-only papers may help ProjectReady understand the literature, but they cannot generate a new author-year citation or reference-list entry.
- If an unconfirmed paper is essential, the model must use a confirmation placeholder instead of inventing citation details.
- Citation-ready papers are still subject to relevance and claim-support checks. They are not cited merely because the student uploaded them.
- Generated citations continue through the fail-closed citation provenance audit and verified reference-list rebuild.

## Source provenance

Each uploaded paper is marked as `uploaded_selected_paper` and records whether citation metadata was:

- verified against a scholarly metadata record, or
- confirmed by the student.

This remains distinct from literature found automatically through OpenAlex, Crossref, Semantic Scholar and ERIC.

## Statistical evidence

Citation-ready selected papers can also supply provisional numerical evidence when an accessible excerpt contains the statistic and the paper has a DOI or stable URL. Such figures remain in the existing red confirmation workflow until the student confirms them.

## Capacity and performance

- Hard project limit: 50 selected papers.
- Existing individual upload-size controls still apply.
- A combined selected-paper upload request has an additional total-size limit, configurable through `PROJECTREADY_SELECTED_PAPERS_TOTAL_BYTES`.
- Stored evidence is compacted rather than retaining every extracted character in every prompt.
- Public project responses omit stored evidence excerpts so restoring the workspace remains lighter.

## New endpoints

- `GET /api/projects/{project_id}/selected-papers`
- `POST /api/projects/{project_id}/selected-papers`
- `PATCH /api/projects/{project_id}/selected-papers/{paper_id}`
- `DELETE /api/projects/{project_id}/selected-papers/{paper_id}`
- `POST /api/chapter-strengthener/extract-selected-papers`
