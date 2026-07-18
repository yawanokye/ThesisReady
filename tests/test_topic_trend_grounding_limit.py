from __future__ import annotations


def _sources(count: int):
    return [
        {
            "title": f"Relevant study {index}",
            "authors": ["Author"],
            "year": 2025,
            "source": "Journal",
            "url": f"https://example.test/{index}",
            "abstract": "Employee competence and administrative performance in public universities.",
            "database": "OpenAlex",
        }
        for index in range(1, count + 1)
    ]


def test_topic_trend_context_uses_configurable_increased_limit(monkeypatch):
    import app.topic_ideas_service as service

    monkeypatch.setenv("PROJECTREADY_TOPIC_TREND_SOURCE_LIMIT", "24")
    context = service._source_context(_sources(30))
    assert len(context) == 24
    assert context[0]["key"] == "S1"
    assert context[-1]["key"] == "S24"


def test_topic_generation_returns_increased_trend_record_count(monkeypatch):
    import app.topic_ideas_service as service

    captured = {}
    monkeypatch.setenv("PROJECTREADY_TOPIC_IDEAS_USE_AI", "0")
    monkeypatch.setenv("PROJECTREADY_TOPIC_TREND_SOURCE_LIMIT", "24")
    monkeypatch.setenv("PROJECTREADY_TOPIC_TREND_SEARCH_LIMIT", "36")

    def fake_search(**kwargs):
        captured["max_results"] = kwargs["max_results"]
        return {
            "query": "employee competence university administrators Ghana",
            "searched_at": "2026-07-18T00:00:00Z",
            "recent_reference_window": "2021-2026",
            "databases": ["OpenAlex"],
            "sources": _sources(30),
            "provider_errors": [],
        }

    monkeypatch.setattr(service, "search_literature_sources", fake_search)
    monkeypatch.setattr(
        service,
        "discover_research_resources",
        lambda payload, ideas: {"ideas": ideas, "resource_search": {"provider_errors": []}},
    )

    result = service.generate_topic_ideas({
        "research_area": "Employee competence and administrative performance",
        "context": "Administrative staff in a Ghanaian public university",
        "country_region": "Ghana",
        "methodology": "Quantitative survey",
        "data_type": "Primary data",
        "level": "Research Masters (e.g. MPhil)",
        "max_ideas": 12,
    })

    assert captured["max_results"] == 36
    assert len(result["source_records_used"]) == 24
    assert result["trend_source_records_used"] == 24
    assert result["trend_source_records_available"] == 30
    assert result["trend_source_record_limit"] == 24
