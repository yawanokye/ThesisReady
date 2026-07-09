# Payment Resume, Target Pages and Long-Chapter Workflow Update

This update improves the Thesis/Dissertation Workspace in three areas raised during testing.

## 1. Payment return now preserves workspace state

Before checkout opens, the workspace now saves a browser-side snapshot of the live form state. The snapshot includes the current project ID, selected chapter, selected sections, section answers, extra instructions, source-search results, extracted revision text, uploaded alignment status, draft output and visible status messages. Password fields and file inputs are not stored.

When Paystack or Stripe returns the user to the workspace, the app restores the project ID, chapter, section selections and entered information. If the payment was triggered by the Develop working draft button, the app records a pending draft action and resumes the draft automatically after a successful payment return.

## 2. Visible target-page controls

The workspace now includes a target-page panel under chapter selection. Users can keep the default page range for the selected level and chapter or choose a custom school/supervisor page target. The selected target is sent to the backend as `chapter_page_targets` and is used by the chapter-length requirement builder when it is marked as custom.

Default targets remain available for Bachelors, Non-Research Masters, Research Masters/MPhil, Professional Doctorate and PhD. Custom targets are treated as planning depth ranges, not permission to add filler.

## 3. Long-chapter staged development is now visible

The UI now explains when staged long-chapter development is active. For long chapters, especially PhD and professional doctorate literature reviews, the workspace shows the staged development flow before drafting. The backend already uses long-chapter requirements to plan, batch and assemble long outputs. The response metrics now also expose the long-chapter strategy so the UI can report that staged planning was used.

For doctoral Chapter Two drafts, the visible plan covers chapter mapping, conceptual review, theory review, empirical review by objective, methodological review, contextual synthesis, contradictions and gaps, conceptual framework and coherence pass.

## Validation

- Python compile check passed.
- JavaScript syntax checks passed for `app.js` and `projectready_payments.js`.
- Test suite passed with `PYTHONPATH=.`: 60 tests passed.
