from __future__ import annotations


def test_topic_idea_generation_cleans_summary_fields_without_name_error(monkeypatch):
    import app.topic_ideas_service as service

    monkeypatch.setenv("PROJECTREADY_TOPIC_IDEAS_USE_AI", "0")
    monkeypatch.setattr(
        service,
        "search_literature_sources",
        lambda **kwargs: {
            "query": "employee competence",
            "searched_at": "2026-07-17T00:00:00Z",
            "recent_reference_window": "2021-2026",
            "databases": ["OpenAlex"],
            "sources": [],
            "provider_errors": [],
        },
    )
    monkeypatch.setattr(
        service,
        "discover_research_resources",
        lambda payload, ideas: {
            "ideas": ideas,
            "resource_search": {"provider_errors": []},
        },
    )

    result = service.generate_topic_ideas(
        {
            "research_area": "  Human   development practices  ",
            "context": "  Administrative staff  ",
            "country_region": " Ghana ",
            "methodology": " Quantitative survey ",
            "data_type": " Primary data ",
            "level": "Bachelors",
            "max_ideas": 2,
        }
    )

    assert result["research_area"] == "Human development practices"
    assert result["context"] == "Administrative staff"
    assert result["country_region"] == "Ghana"
    assert result["methodology"] == "Quantitative survey"
    assert result["data_type"] == "Primary data"
    assert len(result["ideas"]) == 2
