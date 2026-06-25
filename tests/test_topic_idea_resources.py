from app import research_resource_finder as finder


def _ideas():
    return [
        {
            "title": "Financial literacy and retirement planning among informal workers",
            "possible_variables_or_constructs": [
                "financial literacy",
                "financial self-efficacy",
                "retirement planning",
                "income stability",
            ],
            "possible_data_sources": ["survey data"],
        }
    ]


def test_secondary_research_gets_dataset_candidates(monkeypatch):
    monkeypatch.setattr(
        finder,
        "_search_datacite_datasets",
        lambda query, limit: [
            {
                "name": "Household finance survey dataset",
                "provider": "Example Repository",
                "description": "Financial literacy, income and retirement planning variables.",
                "url": "https://example.org/data",
                "source_type": "Live dataset record",
                "discovery_database": "DataCite",
                "access_note": "Check codebook.",
            }
        ],
    )
    monkeypatch.setattr(finder, "_search_harvard_dataverse", lambda query, limit: [])

    payload = {
        "research_area": "financial literacy and retirement planning",
        "context": "informal workers",
        "country_region": "Ghana",
        "methodology": "Secondary data",
        "data_type": "Secondary data available",
    }
    result = finder.discover_research_resources(payload, _ideas())
    guidance = result["ideas"][0]["research_resource_guidance"]

    assert guidance["secondary_data_sources"]
    assert guidance["secondary_data_sources"][0]["name"] == "Household finance survey dataset"
    assert not guidance["questionnaire_or_instrument_sources"]
    assert "DataCite" in result["resource_search"]["databases"]


def test_primary_research_gets_instrument_candidates(monkeypatch):
    monkeypatch.setattr(
        finder,
        "search_literature_sources",
        lambda **kwargs: {
            "databases": ["OpenAlex"],
            "provider_errors": [],
            "sources": [
                {
                    "title": "Development and validation of a financial literacy questionnaire",
                    "authors": ["A. Author"],
                    "year": 2024,
                    "source": "Measurement Journal",
                    "doi": "10.1234/example",
                    "url": "https://doi.org/10.1234/example",
                    "abstract": "A validated questionnaire measuring financial literacy and self-efficacy.",
                    "database": "OpenAlex",
                }
            ],
        },
    )

    payload = {
        "research_area": "financial literacy and retirement planning",
        "context": "informal workers",
        "country_region": "Ghana",
        "methodology": "Quantitative survey",
        "data_type": "Primary data available",
    }
    result = finder.discover_research_resources(payload, _ideas())
    guidance = result["ideas"][0]["research_resource_guidance"]

    assert not guidance["secondary_data_sources"]
    assert guidance["questionnaire_or_instrument_sources"]
    candidate = guidance["questionnaire_or_instrument_sources"][0]
    assert "questionnaire" in candidate["title"].lower()
    assert candidate["matched_constructs"]
    assert "OpenAlex" in result["resource_search"]["databases"]


def test_mixed_methods_can_return_both_resource_types(monkeypatch):
    monkeypatch.setattr(
        finder,
        "_search_datacite_datasets",
        lambda query, limit: [
            {
                "name": "Financial inclusion microdata",
                "provider": "Repository",
                "description": "Financial access and income variables.",
                "url": "https://example.org/microdata",
                "source_type": "Live dataset record",
                "discovery_database": "DataCite",
                "access_note": "Verify licence.",
            }
        ],
    )
    monkeypatch.setattr(finder, "_search_harvard_dataverse", lambda query, limit: [])
    monkeypatch.setattr(
        finder,
        "search_literature_sources",
        lambda **kwargs: {
            "databases": ["Crossref"],
            "provider_errors": [],
            "sources": [
                {
                    "title": "Retirement planning scale validation",
                    "authors": ["B. Researcher"],
                    "year": 2023,
                    "source": "Applied Psychology",
                    "doi": "10.1234/scale",
                    "url": "https://doi.org/10.1234/scale",
                    "abstract": "Psychometric validation of a retirement planning scale.",
                    "database": "Crossref",
                }
            ],
        },
    )

    payload = {
        "research_area": "financial literacy and retirement planning",
        "context": "informal workers",
        "country_region": "Ghana",
        "methodology": "Mixed methods",
        "data_type": "Both primary and secondary data possible",
    }
    result = finder.discover_research_resources(payload, _ideas())
    guidance = result["ideas"][0]["research_resource_guidance"]
    assert guidance["secondary_data_sources"]
    assert guidance["questionnaire_or_instrument_sources"]
