# ProjectReady Flagship Student Upgrade

Date: 15 August 2026

## What this release changes

This upgrade keeps full chapter draft development as a core ProjectReady function and builds a persistent student research workflow around it.

### 1. Student Research Cockpit
- Adds a project readiness view inside the Thesis Workspace.
- Shows chapter progress, research alignment, attached sources and compliance status.
- Recommends the next useful action instead of forcing students to navigate every tool manually.
- Adds a chapter progress navigator and a visible issues panel.

### 2. Research Logic Engine
- Maps objectives to research questions and hypotheses.
- Tracks objective coverage into Chapters Four and Five.
- Flags missing research questions, hypotheses, variables, sources and chapter alignment issues.
- Uses deterministic logic for this monitoring layer, so routine alignment checks do not consume LLM tokens.
- The score is explicitly described as workflow readiness, not an academic grade.

### 3. Chapter drafting retained and strengthened
- `Develop Chapter Draft` remains a primary action.
- Full chapter and selected-section workflows remain available.
- Saved project logic now carries research questions and hypotheses into subsequent work.
- Successful generated or revised drafts automatically create a chapter snapshot.

### 4. Chapter version history
- Stores numbered snapshots of generated and revised chapter drafts.
- Students can inspect earlier versions and restore one without destroying later history.
- A restored version is itself saved as a new snapshot for auditability.

### 5. Project Working File compiler
- Adds `Compile Project Working File DOCX`.
- Combines all currently saved chapter drafts into one editable Word working file.
- Adds a title page, updateable Word table of contents field and working-file audit note.
- Does not consume another paid generation entitlement because it assembles already saved content.

### 6. Research profile persistence
- Adds an API endpoint to save research logic inputs without regenerating a chapter.
- Preserves title, approach, data type, objectives, research questions, hypotheses, variables and other project-level research information.

### 7. Security hardening
- Removes backend Python source files that had been duplicated under the publicly served `/static` folder.
- Removes obsolete `* - Copy.*` production static assets.

### 8. Payment and trial reliability
- Restores explicit Stripe test-mode controls without changing normal live routing.
- Separates Stripe live and test credentials/webhook configuration.
- Restores the controlled Topic Ideas trial-key entitlement flow when the environment key is deliberately configured.

## Validation

- Full automated suite: **157 passed, 0 failed**.
- JavaScript syntax check: passed.
- Python bytecode compilation check: passed.
- Public static directory check: no Python backend files remain.

## Major next-stage flagship modules not included in this patch

These remain the strongest candidates for a subsequent release:
- real cloud student authentication and cross-device project accounts
- supervisor collaboration and correction centre
- Literature Lab with evidence matrices and study-level synthesis
- Analysis Lab with raw-data analysis and statistical interpretation validation
- institutional thesis templates
- proposal-to-thesis conversion workflow
- structured conceptual-framework builder
- final whole-thesis audit and VivaReady
