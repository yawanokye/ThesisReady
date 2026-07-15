from app import source_support


def _profile():
    return {
        "title": "Exchange Rate Movements and Inflation in Ghana",
        "level": "Bachelors",
        "research_area": "exchange-rate pass-through and inflation",
        "study_context": "Ghana",
        "objectives": ["Examine the relationship between exchange-rate movements and inflation"],
        "source_bank": [],
        "automatic_source_support": True,
    }


def test_thin_source_bank_is_enriched_automatically(monkeypatch):
    def fake_search(**kwargs):
        return {
            "databases": ["OpenAlex"],
            "provider_errors": [],
            "sources": [
                {
                    "title": "Exchange-rate pass-through to inflation in Ghana",
                    "authors": ["A. Researcher"],
                    "year": 2024,
                    "source": "Macroeconomic Review",
                    "doi": "10.1234/ghana-pass-through",
                    "abstract": "Evidence on exchange-rate pass-through and inflation in Ghana.",
                    "relevance_tier": "highly_relevant",
                }
            ],
        }
    monkeypatch.setattr(source_support, "search_literature_sources", fake_search)
    profile = _profile()
    result = source_support.ensure_automatic_source_support(profile, 1)
    assert result["searched"] is True
    assert profile["source_bank"]
    assert profile["retrieved_sources"]["automatic"] is True


def test_existing_evidence_bank_avoids_repeated_search(monkeypatch):
    profile = _profile()
    profile["source_bank"] = [
        {"title": f"Relevant source {i}", "doi": f"10.1/{i}", "relevance_tier": "highly_relevant"}
        for i in range(12)
    ]
    monkeypatch.setattr(source_support, "search_literature_sources", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not search")))
    result = source_support.ensure_automatic_source_support(profile, 1)
    assert result["searched"] is False
    assert result["source_count"] == 12


def test_project_can_disable_automatic_source_support(monkeypatch):
    profile = _profile()
    profile["automatic_source_support"] = False
    result = source_support.ensure_automatic_source_support(profile, 1)
    assert result["enabled"] is False
