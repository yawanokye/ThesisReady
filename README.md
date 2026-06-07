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
OPENAI_MODEL=gpt-5.5
DATABASE_URL=projectready.db
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
Add payment and plan limits.
Local fallback mode
When no OpenAI API key is configured, the app still runs. It creates structured placeholder drafts from the selected template. This is useful for demos, but real drafting requires an API key.
