# ProjectReady AI Academic Integrity and Guided Workspace Update

This update aligns ProjectReady AI with a self-service academic research-support model.

## Thesis Workspace

- Repositions the module as guided working-draft development rather than completed thesis writing.
- Requires an academic-integrity declaration and a user-contribution declaration.
- Blocks blank or minimally supplied requests from producing long chapters.
- Requires meaningful research context, research logic and student-supplied evidence or judgement.
- Requires actual uploaded results for Chapter Four.
- Sends the latest workspace inputs to the backend before development, so edits made after project creation are retained.
- Labels generated and exported content as editable AI-assisted working drafts.

## Responsible-use controls

- Adds `/academic-integrity` with explicit permitted and prohibited uses.
- States that Anovlad Technologies does not provide ghostwriting, assignment completion, fabricated research or completed academic work.
- Updates registration, landing, payment and Chapter Strengthener wording.
- Adds the responsible-use notice to chapter and strengthening DOCX exports.

## Database persistence correction

A plain SQLite path supplied through `DATABASE_URL`, such as `/var/data/projectready.db`, is now honoured. The previous build ignored non-PostgreSQL values in `DATABASE_URL` and continued writing to `projectready.db` in the temporary application directory.

Recommended Render configuration:

```env
DATABASE_URL=/var/data/projectready.db
```

with a persistent disk mounted at `/var/data`.

## Payment-record durability

The payment store now uses the same database path resolver as the main project store. With a Render disk mounted at `/var/data`, use:

```env
DATABASE_URL=/var/data/projectready.db
```

This path is honoured for project profiles, recovery records, purchase records, webhook event deduplication and entitlement usage. Startup logs now show both the main database backend and the payment database backend, making accidental writes to the temporary application directory easy to detect.

## Validation completed

- 39 automated tests passed.
- All Python modules compiled successfully.
- Main browser JavaScript files passed syntax validation.
- The home page, Thesis Workspace, Chapter Strengthener, Academic Integrity page, Terms page and health endpoint passed route smoke tests.
- A storage smoke test confirmed that both the project database and payment database use the same configured persistent SQLite path.
