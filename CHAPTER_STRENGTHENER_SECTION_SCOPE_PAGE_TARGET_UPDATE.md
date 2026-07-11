# Chapter Strengthener section scope and page target update

## Added

- Standard optional sections are loaded for the selected chapter from the same template used by the Thesis Workspace.
- Each standard section can be marked **Strengthen existing** or **Add if missing**.
- Users can add custom new sections with section-specific instructions.
- Output scope can be the complete selected chapter or only selected sections.
- Complete-thesis uploads are deterministically isolated to the selected numbered chapter before revision. Other chapters are not returned.
- The complete thesis remains available only as alignment context.
- Users can set a custom target page range from 1 to 120 pages.
- In selected-sections mode, the page target applies to the selected-section output.
- Selected-section output is stored in the Chapter Strengthener record and does not overwrite the complete saved project chapter.

## New request fields

- `uploaded_content_scope`
- `strengthening_scope`
- `selected_section_ids` / `selected_section_titles`
- `new_section_ids` / `new_section_titles`
- `custom_new_sections`
- `custom_target_pages_enabled`
- `target_page_min` / `target_page_max`
