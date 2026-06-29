from __future__ import annotations

from app import source_finder as finder


def _record(title: str, abstract: str = "", *, year: int = 2024, database: str = "OpenAlex", doi: str = ""):
    return {
        "title": title,
        "abstract": abstract,
        "year": year,
        "database": database,
        "doi": doi,
        "source": "Test Journal",
        "authors": ["Test Author"],
        "citation_count": 5,
    }


def test_exchange_pass_through_gate_rejects_country_only_matches(monkeypatch):
    records = [
        _record(
            "Asymmetric Exchange Rate Pass-Through to Consumer Prices in Ghana",
            "The paper estimates exchange rate pass-through to inflation.",
            doi="10.1/relevant",
        ),
        _record(
            "Buyer Market Power and Exchange Rate Pass-through",
            "The response of prices to exchange rate changes depends on buyer power.",
            doi="10.1/comparative",
        ),
        _record(
            "Improving Agricultural Extension Services in Ghana",
            "The study examines climate adaptation among farmers.",
            doi="10.1/unrelated1",
        ),
        _record(
            "The Impact of Free Secondary Education in Ghana",
            "The study examines scholarships and educational attainment.",
            database="ERIC",
            doi="10.1/unrelated2",
        ),
        _record(
            "Effects of Exchange Rate Regimes on FDI Inflows in Ghana",
            "The paper studies exchange rate regimes and foreign investment.",
            doi="10.1/tangential",
        ),
    ]

    monkeypatch.setattr(finder, "_search_openalex", lambda query, per_provider: records)
    monkeypatch.setattr(finder, "_search_crossref", lambda query, per_provider: [])
    monkeypatch.setattr(finder, "_search_semantic_scholar", lambda query, per_provider: [])

    eric_called = {"value": False}

    def _eric(query, per_provider):
        eric_called["value"] = True
        return []

    monkeypatch.setattr(finder, "_search_eric", _eric)

    result = finder.search_literature_sources(
        profile={"title": "exchange pass-through in Ghana"},
        max_results=60,
    )

    titles = {src["title"] for src in result["sources"]}
    assert "Asymmetric Exchange Rate Pass-Through to Consumer Prices in Ghana" in titles
    assert "Buyer Market Power and Exchange Rate Pass-through" in titles
    assert "Improving Agricultural Extension Services in Ghana" not in titles
    assert "The Impact of Free Secondary Education in Ghana" not in titles
    assert "Effects of Exchange Rate Regimes on FDI Inflows in Ghana" not in titles
    assert result["count"] == 2
    assert result["requested_count"] == 60
    assert result["rejected_irrelevant_count"] == 3
    assert eric_called["value"] is False


def test_long_multi_construct_query_keeps_construct_specific_sources(monkeypatch):
    records = [
        _record(
            "Financial Literacy and Retirement Planning Behaviour",
            "Financial literacy predicts retirement planning.",
            doi="10.2/full",
        ),
        _record(
            "Development and Validation of a Financial Literacy Scale",
            "A measure of financial literacy.",
            doi="10.2/literacy",
        ),
        _record(
            "Retirement Planning Scale Validation",
            "A retirement planning preparedness scale.",
            doi="10.2/retirement",
        ),
        _record(
            "Social Health Insurance in Ghana",
            "Health insurance access and affordability.",
            doi="10.2/unrelated",
        ),
    ]

    monkeypatch.setattr(finder, "_search_openalex", lambda query, per_provider: records)
    monkeypatch.setattr(finder, "_search_crossref", lambda query, per_provider: [])
    monkeypatch.setattr(finder, "_search_semantic_scholar", lambda query, per_provider: [])
    monkeypatch.setattr(finder, "_search_eric", lambda query, per_provider: [])

    result = finder.search_literature_sources(
        profile={
            "title": "Financial literacy and retirement planning among informal workers in Ghana"
        },
        max_results=10,
    )

    by_title = {src["title"]: src for src in result["sources"]}
    assert by_title["Financial Literacy and Retirement Planning Behaviour"]["relevance_tier"] == "highly_relevant"
    assert by_title["Development and Validation of a Financial Literacy Scale"]["relevance_tier"] == "partly_relevant"
    assert by_title["Retirement Planning Scale Validation"]["relevance_tier"] == "partly_relevant"
    assert "Social Health Insurance in Ghana" not in by_title


def test_explicit_terms_are_not_diluted_by_broader_project_title():
    query = finder.build_source_query(
        {
            "title": "A broad study of exchange rates, inflation, monetary policy and unemployment in Ghana",
            "research_area": "macroeconomics",
        },
        user_query="exchange rate pass-through to consumer prices",
    )
    assert query == "exchange rate pass-through to consumer prices"
