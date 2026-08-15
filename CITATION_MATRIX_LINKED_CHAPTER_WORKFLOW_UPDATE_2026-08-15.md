# ProjectReady AI, Citation Matrix and Linked-Chapter Workflow Upgrade

Date: 15 August 2026

## 1. Adaptive citation-density matrix

ProjectReady now uses a discipline-and-section citation-density matrix measured as individual referenced works per 1,000 substantive words.

| Discipline | Introduction | Literature Review | Methodology | Results & Discussion | Conclusion |
|---|---:|---:|---:|---:|---:|
| STEM | 5–10 | 15–25 | 2–5 | 8–15 | 0–3 |
| Social Sciences | 8–12 | 20–35 | 4–8 | 12–20 | 2–5 |
| Humanities | 10–15 | 25–40 | 1–3 | 15–25 | 3–6 |
| Professional & Health, including Nursing and Business | 8–15 | 20–30 | 5–10 | 10–18 | 1–4 |

The workspace allows automatic discipline detection or manual selection. Chapter Strengthener infers the matrix from the discipline/programme field. Results-only, objectives, research questions and other research-logic sections remain citation-light and are not padded to meet a chapter-level range.

## 2. Zero-fabrication citation gate

Citation density is a guide, not a quota. ProjectReady now fails closed on generated citations.

- A new citation must map to a structured retrieved source record or a citation already supplied by the student.
- Unknown model-generated author-year citations are removed and replaced by a precise source-needed placeholder.
- Model-created reference-list entries are discarded. The final reference list is rebuilt only from retrieved source metadata and reference entries supplied by the user.
- Missing author, title, DOI, journal, volume, issue, page, URL, quotation, finding or statistic is never guessed.
- If the evidence bank cannot meet the matrix range, the draft remains below target and reports the evidence gap.
- Group citations are counted by individual works, so three sources in one parenthetical group count as three referenced works.

## 3. Chapter 1 to Chapter 2 continuation

After a complete standard Chapter 1 has been developed and saved, the workspace asks whether the student wants to add Chapter 2.

Selecting **Yes, continue to the next chapter** automatically carries forward and links:

- current research title
- objectives
- research questions
- hypotheses
- variables or constructs
- study context
- research approach
- saved Chapter 1 text as cross-chapter alignment context
- citation-matrix discipline and target for the next chapter

The same linked workflow continues from Chapter 2 to later chapters where applicable.

A selected-section draft does not trigger the next-chapter prompt. The prompt appears only after the complete standard chapter has been developed.

## 4. Change or add information before continuing

The continuation panel includes an expandable correction area. The student can update the title, context, objectives, questions, hypotheses, variables, research approach and additional transition instructions before ProjectReady begins the next chapter. The updated information is persisted in the project profile and used for later cross-chapter alignment.

## 5. Sourced statistical evidence requiring confirmation

ProjectReady may suggest a numerical fact only when that exact numerical statement appears in accessible text attached to a structured source record with a DOI or stable source URL.

It never estimates or invents a statistic. A pending statistic used in a draft is kept in a bracketed confirmation marker with the source label and locator. The browser preview and DOCX attention rendering show the marker in red. The continuation panel lists sourced statistics actually used in the completed chapter and asks the student to confirm or reject them.

Confirmed statistics become eligible for later chapter use. Rejected statistics are excluded from future suggestions. If no suitable sourced statistic is available, ProjectReady inserts a precise request for a verified statistic and source instead of guessing.

## 6. Chapter Strengthener

Chapter Strengthener now uses the same citation-density matrix and fail-closed citation rules. Its citation target responds to the discipline/programme and chapter type. It may add a new source only from the verified source bank, and the final reference list is rebuilt from verified metadata plus user-supplied references.

## 7. Validation

The upgraded build passes 173 automated tests, Python compilation, JavaScript syntax checks, HTML duplicate-ID checks and the public static source-code exposure check.
