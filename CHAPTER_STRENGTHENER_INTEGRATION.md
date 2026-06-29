# Integrated Chapter Strengthener

The ArticleReady AI revision engine has been integrated into the existing ProjectReady AI FastAPI service. No second Render web service is required.

## User route

- `/chapter-strengthener`
- Alias: `/strengthen-chapter`

## API routes

- `POST /api/chapter-strengthener/extract-file`
- `POST /api/chapter-strengthener/targets`
- `POST /api/projects/{project_id}/chapter-strengthener/revise`
- `POST /api/projects/{project_id}/chapter-strengthener/export`

## Existing payment integration

The revision endpoint consumes the paid chapter's included `revision` entitlement. The DOCX endpoint consumes the included `export` entitlement. The same purchase ID and access token already stored by `projectready_payments.js` are used.

## Project integration

The page restores the current project from `projectready-current-project`, pre-fills research details and attached source records, can load a saved chapter draft, and saves the strengthened chapter back as the project's current chapter draft when selected.

## DOCX display

- Blue: wording added or changed by ProjectReady AI
- Black: exact unchanged wording
- Red: student or supervisor action required
- Markdown emphasis is converted to real Word bold and italics

## Render

Continue using the existing build and start commands. Add the chapter revision environment variables from `.env.example`. No new Render service or domain is required.
