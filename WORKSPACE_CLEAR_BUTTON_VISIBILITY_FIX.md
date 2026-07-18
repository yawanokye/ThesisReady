# Thesis Workspace clear-button visibility fix

The Thesis Workspace now guarantees that **Clear and start new job** is visible beside **Create research project**.

## Changes

- Keeps the button in `workspace.html`.
- Adds a JavaScript fallback that creates the button if an older cached HTML document omits it.
- Forces the button to remain visible through dedicated CSS.
- Adds `Cache-Control: no-store` to the public Workspace and Chapter Strengthener HTML routes.
- Updates static asset versions so browsers request the corrected JavaScript and CSS.
- Keeps the existing clean-job behaviour, including removing the stored project ID and background-job records.
