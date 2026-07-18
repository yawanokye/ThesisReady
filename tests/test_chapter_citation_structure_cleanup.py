from app.ai_service import (
    _clean_chapter_references,
    _finalise_output_controls,
    _normalise_objectives_and_questions,
    _normalise_purpose_of_study,
)
from app.chapter_revision_service import chapter_planning_targets
from app.compliance import check_chapter


def test_purpose_is_reduced_to_one_concise_sentence():
    text = """## 1.4 Purpose of the Study
The purpose of the study was to examine the relationship between training and performance among administrators. Specifically, the section explains why the study is important. This purpose also supports an advanced analytical design.

## 1.5 Research Objectives
1. To assess training.
"""
    cleaned = _normalise_purpose_of_study(text)
    purpose_body = cleaned.split("## 1.5 Research Objectives", 1)[0]
    assert "The purpose of the study was to examine" in purpose_body
    assert "Specifically" not in purpose_body
    assert "advanced analytical design" not in purpose_body


def test_objective_commentary_is_removed_and_questions_restart_at_one():
    text = """## 1.5.2 Specific Objectives
1. To assess training relevance. This objective supports an MPhil-level analysis.
2. To examine employee competence. The second objective permits regression analysis.
These objectives provide sufficient analytical depth.

## 1.6 Research Questions
What is the level of training relevance? 2. What is the level of employee competence? 3. How are the constructs related?
These questions align with the design.
"""
    cleaned = _normalise_objectives_and_questions(text)
    assert "MPhil-level" not in cleaned
    assert "regression analysis" not in cleaned
    assert "sufficient analytical depth" not in cleaned
    assert "These questions align" not in cleaned
    assert "1. What is the level of training relevance?" in cleaned
    assert "2. What is the level of employee competence?" in cleaned
    assert "3. How are the constructs related?" in cleaned


def test_references_are_clean_deduplicated_alphabetised_and_audit_removed():
    text = """# References
- Zeta, A. (2022). Last work. Journal.
1. Alpha, B. (2021). First work. Journal.
- Zeta, A. (2022). Last work. Journal.

# Source Use Audit
| Source Key | Decision |
|---|---|
| S1 | Cited |
"""
    cleaned = _clean_chapter_references(text)
    assert "Source Use Audit" not in cleaned
    assert "Source Key" not in cleaned
    assert cleaned.count("Zeta, A. (2022)") == 1
    assert cleaned.index("Alpha, B. (2021)") < cleaned.index("Zeta, A. (2022)")
    assert "- Zeta" not in cleaned
    assert "1. Alpha" not in cleaned


def test_final_output_applies_all_chapter_one_controls():
    text = """# CHAPTER 1
# INTRODUCTION

## 1.4 Purpose of the Study
The purpose of the study was to examine X and Y. This paragraph is unnecessary commentary.

## 1.5 Research Objectives
1. To assess X. This objective supports the selected level.
2. To examine Y.

## 1.6 Research Questions
What is X? 2. How is X related to Y?

# References
- Zulu, A. (2024). Z work.
- Able, B. (2023). A work.
"""
    cleaned = _finalise_output_controls(text)
    assert "unnecessary commentary" not in cleaned
    assert "selected level" not in cleaned
    assert "1. What is X?" in cleaned
    assert "2. How is X related to Y?" in cleaned
    assert cleaned.index("Able, B. (2023)") < cleaned.index("Zulu, A. (2024)")


def test_strengthener_uses_higher_citation_targets():
    target = chapter_planning_targets("Bachelors", "1. Introduction")
    assert target["citation_density_per_1000_words"] == {"minimum": 12, "maximum": 16}


def test_compliance_does_not_require_source_use_audit():
    result = check_chapter(1, [], "# References\n\nAble, B. (2023). A work.")
    assert all(item.get("section_id") != "source_use_audit" for item in result["items"])
