# Evidence efficiency and non-blocking export update

Claim Support Review remains active in both Draft Development and Chapter Strengthener, but it is no longer a hard prerequisite for Word export. Students can export a working DOCX while unresolved evidence items remain visible for reading, source checking and supervisor discussion. Project Working File compilation is also allowed with unresolved evidence-review items.

Both workflows now provide checkbox selection, Select all unresolved items, and Ignore selected. Bulk Ignore removes selected items from the current review and clears matching source-needed placeholders where present. Ignore does not verify a claim and never creates a citation.

The 50-paper selected-literature limit remains unchanged. Every uploaded paper is represented in a compact locally derived evidence capsule so the complete collection can shape chapter planning and synthesis. Only the most relevant original evidence passages are sent to the writing model for the active section. For long chapters, the planning pass sees the compact map of all uploaded papers once, while each drafting chunk receives section-relevant passages only.

Default controls are PROJECTREADY_SELECTED_PAPERS_PER_SECTION=8, PROJECTREADY_SELECTED_PAPER_PROMPT_CHARS=1400, and PROJECTREADY_SELECTED_PAPER_CAPSULE_CHARS=520. These are prompt-context controls, not limits on how many uploaded papers may inform the project.

Uploaded-paper source-bank mirrors are now metadata/capsule based instead of duplicating the large evidence excerpt. Claim Support Review and provisional-statistics checks retrieve the original uploaded-paper evidence directly when needed.

To reduce duplicate API spend after model timeouts, the default background-job attempts are now one. Automatic retry of expensive timeout jobs and same-model safe retries are opt-in. The relevant defaults are PROJECTREADY_JOB_MAX_ATTEMPTS=1, PROJECTREADY_RETRY_MODEL_TIMEOUT_JOBS=0, PROJECTREADY_CHAPTER_REVISION_MODEL_ATTEMPTS=1, and PROJECTREADY_SAFE_MODEL_RETRY=0.

Academic safeguards remain unchanged: only verified or user-confirmed sources may create new citations, detailed claims require accessible supporting evidence, citation-density directives remain active, and no paper is forced into the writing or reference list merely because it was uploaded.
