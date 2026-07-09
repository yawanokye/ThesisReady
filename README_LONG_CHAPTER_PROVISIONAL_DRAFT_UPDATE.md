# Long-Chapter and Provisional Drafting Update

This update improves ProjectReady AI's thesis-writing workflow for very long chapters, especially doctoral and PhD literature reviews.

## Main changes

1. Provisional draft support
   - The app still encourages students to provide their own research area, context, objectives, sources, evidence, supervisor comments and writing direction.
   - When these inputs are limited, drafting is no longer blocked after the required integrity declarations and section selection are completed.
   - The system prepares a working draft for the user's consideration and marks missing facts, sources, methods, results, institutional details or alignment issues with bracketed placeholders.
   - Chapter Four without uploaded results is treated as provisional and must use placeholder tables/action notes rather than invented findings.

2. Long-chapter staged development
   - Very long chapters now carry a `long_chapter_strategy` in the drafting prompt.
   - PhD and doctoral literature reviews are treated as staged development projects rather than one whole-chapter pass.
   - The strategy directs the model to build conceptual, theoretical, empirical, methodological, contextual, contradiction, gap and framework coverage separately.
   - Default chunking was adjusted from broad 8,000-word groups to smaller 3,000-word section batches with up to 10 chunks.
   - A compact long-chapter plan is generated before chunk drafting where the AI provider is available.

3. Literature review depth protection
   - Chapter Two weights now match the actual template section IDs.
   - The empirical review, theory review and conceptual review receive deeper word budgets for doctoral work.
   - Broad sections can be subdivided into meaningful lower-level headings so a PhD literature review does not become a short annotated overview.

4. Chapter Strengthener support
   - The Chapter Strengthener now includes a long-chapter strengthening strategy for very long doctoral chapters.
   - Missing but necessary sections can still be inserted when justified and marked in red through bracketed confirmation placeholders.
   - Long doctoral literature reviews are checked separately for conceptual, theoretical, empirical, methodological, contextual, gap and framework coverage.

## Validation

- Python compile checks passed.
- JavaScript syntax checks passed.
- Full test suite passed: 60 tests.
