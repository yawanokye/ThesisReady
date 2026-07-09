# UI restore, page target, Chapter One autofill and Topic Ideas price update

This update restores the workspace UI behaviours that were missing after the live-payment merge while keeping the live Paystack and Stripe payment routing.

## Restored workspace controls

- Restored custom page-target controls in the Thesis Workspace.
- Users can keep the default level/chapter page target or set a custom minimum and maximum page range for the active chapter.
- The custom range is stored in the project profile and passed to the generation service.
- Very long chapters still use staged section-batch generation rather than one shallow pass.

## Chapter One / Introduction autofill

- Added an Introduction / Chapter One upload panel in the project setup section.
- Added `/api/projects/extract-introduction-profile`.
- The endpoint extracts text from `.docx`, `.pdf`, `.txt` and `.md` files and returns suggested values for:
  - title,
  - research area,
  - study context,
  - objectives,
  - research questions,
  - variables or constructs.
- The frontend supports two modes:
  - fill empty fields only,
  - replace matching fields.

## Topic Ideas price display

- Ghana now displays **GHS 10** in the Topic Ideas interface.
- Outside Ghana still displays **US$1.50**.
- The live routing remains unchanged:
  - Ghana uses Paystack,
  - outside Ghana uses Stripe.

## Validation

- Python compile checks passed.
- JavaScript syntax checks passed.
- Test suite passed with `PYTHONPATH=.`: 56 tests passed.
