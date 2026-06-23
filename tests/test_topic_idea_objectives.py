from app.topic_ideas_service import _ensure_level_appropriate_objectives


def _idea():
    return {
        "title": "Digital Financial Literacy and Retirement Planning among Informal Workers",
        "possible_variables_or_constructs": [
            "digital financial literacy",
            "financial self-efficacy",
            "retirement planning",
            "income stability",
        ],
    }


def test_required_specific_objective_counts_by_level():
    expected = {
        "Bachelors": 4,
        "Non-Research Masters": 4,
        "Research Masters (e.g. MPhil)": 5,
        "Professional Doctorate (e.g. DBA, DEd)": 5,
        "PhD": 6,
    }
    for level, count in expected.items():
        payload = {
            "level": level,
            "research_area": "digital financial literacy and retirement planning",
            "context": "informal workers in Ghana",
            "methodology": "Quantitative survey",
        }
        result = _ensure_level_appropriate_objectives(payload, _idea())
        objectives = result["proposed_objectives"]
        assert objectives["general_objective"].startswith("To ")
        assert len(objectives["specific_objectives"]) == count
        assert all(item.startswith("To ") for item in objectives["specific_objectives"])
        assert objectives["level_alignment"]


def test_existing_ai_objectives_are_preserved_and_completed():
    payload = {
        "level": "Research Masters (e.g. MPhil)",
        "research_area": "digital financial literacy",
        "context": "informal workers in Ghana",
        "methodology": "Quantitative survey",
    }
    idea = _idea()
    idea["proposed_objectives"] = {
        "general_objective": "examine digital financial literacy and retirement planning",
        "specific_objectives": [
            "assess digital financial literacy",
            "test the relationship between financial self-efficacy and retirement planning",
        ],
        "level_alignment": "Custom alignment note",
    }
    result = _ensure_level_appropriate_objectives(payload, idea)
    objectives = result["proposed_objectives"]
    assert objectives["general_objective"].startswith("To examine")
    assert objectives["specific_objectives"][0].startswith("To assess")
    assert len(objectives["specific_objectives"]) == 5
    assert objectives["level_alignment"] == "Custom alignment note"
