ProjectReady AI
ProjectReady AI is a starter MVP for a customisable academic project-work writing and compliance assistant.
It lets a student:
Create a project profile.
Choose a chapter.
Select the sections required under that chapter.
Answer guided questions for each section.
Generate a chapter draft using OpenAI when configured.
Run a basic compliance check against the selected guideline rules.
Export the chapter and compliance report as DOCX files.
The included default template is adapted from a thesis self-evaluation checklist. It covers Chapter One to Chapter Five and allows institutions to customise sections and rules.
Important academic integrity note
This app is designed as a drafting and compliance-support tool. It should not be used to fabricate data, citations, ethical approval, results, or supervisor-approved content. Students remain responsible for the originality, evidence, analysis, and final submission.
Folder structure
```text
projectready_ai/
├── app/
│   ├── data/default_template.json
│   ├── routers/
│   │   ├── generation.py
│   │   ├── projects.py
│   │   └── templates.py
│   ├── static/
│   │   ├── app.js
│   │   ├── index.html
│   │   └── styles.css
│   ├── ai_service.py
│   ├── compliance.py
│   ├── database.py
│   ├── export.py
│   ├── main.py
│   ├── schemas.py
│   └── template_store.py
├── .env.example
├── README.md
└── requirements.txt
```
Setup
Create a virtual environment:
```bash
python -m venv .venv
```
Activate it:
```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```
Install packages:
```bash
pip install -r requirements.txt
```
Create your environment file:
```bash
cp .env.example .env
```
Open `.env` and add your OpenAI API key:
```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6-terra
# Render production, single instance with persistent disk mounted at /var/data:
DATABASE_URL=/var/data/projectready.db
# Local development fallback when DATABASE_URL is blank:
PROJECTREADY_SQLITE_DB_PATH=projectready.db
APP_NAME=ProjectReady AI
```
Run the app:
```bash
uvicorn app.main:app --reload
```
Open this address in your browser:
```text
http://127.0.0.1:8000
```
API endpoints
Templates
```http
GET /api/templates/default
GET /api/templates/default/chapters/{chapter_number}
```
Projects
```http
POST /api/projects
GET /api/projects
GET /api/projects/{project_id}
POST /api/projects/{project_id}/sections
```
Drafting and checking
```http
POST /api/projects/{project_id}/draft
POST /api/projects/{project_id}/check
GET /api/projects/{project_id}/export/chapter/{chapter_number}
GET /api/projects/{project_id}/export/check/{chapter_number}
```
Customising the guideline
Edit:
```text
app/data/default_template.json
```
Each chapter contains section groups. Each section has:
`section_id`
`section_title`
`default_selected`
`guiding_questions`
`rules`
Example:
```json
{
  "section_id": "ch1_problem",
  "section_title": "Statement of the Problem",
  "default_selected": true,
  "guiding_questions": [
    "What exactly is the research problem?",
    "What evidence shows that the problem exists?"
  ],
  "rules": [
    "State a clear, specific, researchable problem rather than a broad description.",
    "Support the problem with empirical, practical, or policy evidence."
  ]
}
```
Suggested next improvements
Add user authentication and roles for student, supervisor, department, and admin.
Add institutional template creation in the admin interface.
Improve the compliance checker with LLM-assisted evidence mapping.
Add full project export with automatic table of contents.
Add citation and reference checking by connecting it to CiteIntegrity.
Add supervisor comment workflow.
Add final page and paragraph mapping after DOCX/PDF pagination.
Local fallback mode
When no OpenAI API key is configured, the app still runs. It creates structured placeholder drafts from the selected template. This is useful for demos, but real drafting requires an API key.

## Chapter payment setup

The thesis workspace now supports one-off payment per project chapter.

- Free Starter: one Chapter One draft with up to five selected sections
- Bachelors Project: US$4.99 per chapter
- Masters Dissertation / MPhil Thesis: US$9.99 per chapter
- Professional Doctorate / PhD: US$19.99 per chapter

Each paid chapter includes one guided working draft, one strengthening revision, one compliance review and one editable chapter DOCX export. Purchases remain valid for 90 days and are tied to the selected project and chapter.

### Render database

The commercial web service and background worker must share one Render PostgreSQL database. Set the same PostgreSQL internal connection URL as `DATABASE_URL` on both services. SQLite remains suitable only for local development or a single-process test deployment. Do not use separate SQLite files when the background worker is enabled because the web service and worker would not share jobs, projects or entitlements.

### Required production variables

```text
APP_BASE_URL=https://projectreadyai.com
DATABASE_URL=<Render PostgreSQL internal connection URL>
PAYSTACK_SECRET_KEY=<Paystack live secret key>
STRIPE_LIVE_SECRET_KEY=<Stripe live secret key>
STRIPE_LIVE_WEBHOOK_SECRET=<Stripe endpoint signing secret>
```

Configure fixed GHS Paystack amounts with:

```text
PROJECTREADY_PAYSTACK_BACHELORS_GHS=<approved amount>
PROJECTREADY_PAYSTACK_MASTERS_GHS=<approved amount>
PROJECTREADY_PAYSTACK_DOCTORATE_GHS=<approved amount>
```

Webhook endpoints:

```text
https://projectreadyai.com/payment/paystack/webhook
https://projectreadyai.com/payment/stripe/webhook
```

Paystack callback:

```text
https://projectreadyai.com/payment/paystack/callback
```

Stripe events to subscribe to:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
```

## Project recovery and external chapter strengthening

ProjectReady AI now supports email-and-PIN Project ID recovery without a paid email service. New projects can save a recovery email and 6-digit PIN, and existing projects can enable recovery from the Thesis Workspace.

The Chapter Strengthener also supports chapters created outside ProjectReady AI. It automatically creates a recoverable revision-only project and uses a lower-cost revision-only purchase containing one strengthening revision, one compliance check and one DOCX export.

See `PROJECT_RECOVERY_AND_REVISION_ONLY_UPDATE.md` for configuration and routes.
