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
                "name": "Financial literacy and retirement planning microdata",
                "provider": "Repository",
                "description": "Financial literacy, retirement planning and income stability variables for informal workers in Ghana.",
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


def test_unrelated_dataset_and_country_only_portal_are_excluded(monkeypatch):
    monkeypatch.setattr(
        finder,
        "_search_datacite_datasets",
        lambda query, limit: [
            {
                "name": "Agricultural crop yield archive",
                "provider": "Example Repository",
                "description": "Maize, rainfall and soil fertility observations.",
                "url": "https://example.org/agriculture",
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

    assert guidance["secondary_data_sources"] == []
    assert all("Ghana Statistical Service" not in item for item in result["ideas"][0]["possible_data_sources"])
    assert result["ideas"][0]["possible_data_sources"] == []


def test_unrelated_instrument_is_not_attached(monkeypatch):
    monkeypatch.setattr(
        finder,
        "search_literature_sources",
        lambda **kwargs: {
            "databases": ["OpenAlex"],
            "provider_errors": [],
            "sources": [
                {
                    "title": "Teacher classroom management questionnaire validation",
                    "authors": ["C. Author"],
                    "year": 2024,
                    "source": "Education Measurement",
                    "doi": "10.1234/unrelated",
                    "url": "https://doi.org/10.1234/unrelated",
                    "abstract": "Validation of a classroom management questionnaire for teachers.",
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

    assert guidance["questionnaire_or_instrument_sources"] == []
    directions = " ".join(result["ideas"][0]["possible_data_sources"]).lower()
    assert "financial literacy" in directions
    assert "informal workers" in directions


def test_resource_queries_are_built_for_each_individual_idea(monkeypatch):
    queries = []

    def fake_search(**kwargs):
        queries.append(kwargs["query"])
        return {"databases": ["Crossref"], "provider_errors": [], "sources": []}

    monkeypatch.setattr(finder, "search_literature_sources", fake_search)
    ideas = [
        {
            "title": "Financial literacy and retirement planning among informal workers",
            "possible_variables_or_constructs": ["financial literacy", "retirement planning"],
        },
        {
            "title": "Mobile money fraud awareness and consumer protection among traders",
            "possible_variables_or_constructs": ["fraud awareness", "consumer protection"],
        },
    ]
    payload = {
        "research_area": "personal finance and digital financial services",
        "context": "informal workers and traders",
        "country_region": "Ghana",
        "methodology": "Quantitative survey",
        "data_type": "Primary data available",
    }

    result = finder.discover_research_resources(payload, ideas)

    assert len(queries) == 2
    assert "retirement planning" in queries[0].lower()
    assert "fraud awareness" in queries[1].lower()
    assert result["resource_search"]["strategy"] == "per_idea_strict"
    assert len(result["resource_search"]["per_idea_searches"]) == 2


def test_not_sure_data_access_does_not_trigger_secondary_dataset_search(monkeypatch):
    calls = {"datasets": 0}

    def unexpected_dataset_search(query, limit):
        calls["datasets"] += 1
        return []

    monkeypatch.setattr(finder, "_search_datacite_datasets", unexpected_dataset_search)
    monkeypatch.setattr(finder, "_search_harvard_dataverse", unexpected_dataset_search)
    monkeypatch.setattr(
        finder,
        "search_literature_sources",
        lambda **kwargs: {"databases": [], "provider_errors": [], "sources": []},
    )
    payload = {
        "research_area": "human development practices and employee performance",
        "context": "administrative staff in a public university",
        "country_region": "Ghana",
        "methodology": "Quantitative survey",
        "data_type": "Not sure",
    }
    result = finder.discover_research_resources(payload, [{
        "title": "Employee competence and administrative performance in a Ghanaian public university",
        "possible_variables_or_constructs": ["employee competence", "administrative performance"],
    }])
    guidance = result["ideas"][0]["research_resource_guidance"]
    assert calls["datasets"] == 0
    assert guidance["secondary_data_sources"] == []
    assert guidance["show_secondary_data"] is False


def test_generic_employee_or_performance_dataset_is_rejected(monkeypatch):
    monkeypatch.setattr(
        finder,
        "_search_datacite_datasets",
        lambda query, limit: [
            {
                "name": "Employee Ownership Trusts and Perpetual Purpose Trusts in the United States",
                "provider": "Unrelated repository",
                "description": "A working database of employee ownership and workplace democracy trusts in the United States.",
                "url": "https://example.org/unrelated",
                "source_type": "Live dataset record",
                "discovery_database": "DataCite",
                "access_note": "Check files.",
            },
            {
                "name": "Throttling JavaScript background timers to improve performance",
                "provider": "Software repository",
                "description": "Browser timer performance and battery-life experiment.",
                "url": "https://example.org/browser",
                "source_type": "Live dataset record",
                "discovery_database": "DataCite",
                "access_note": "Check files.",
            },
        ],
    )
    monkeypatch.setattr(finder, "_search_harvard_dataverse", lambda query, limit: [])
    payload = {
        "research_area": "human development practices and employee performance",
        "context": "administrative staff in a public university",
        "country_region": "Ghana",
        "methodology": "Secondary data",
        "data_type": "Secondary data available",
    }
    idea = {
        "title": "Employee competence and administrative performance in a Ghanaian public university",
        "possible_variables_or_constructs": [
            "employee competence",
            "administrative performance",
            "job knowledge",
            "functional skills",
        ],
    }
    result = finder.discover_research_resources(payload, [idea])
    guidance = result["ideas"][0]["research_resource_guidance"]
    assert guidance["secondary_data_sources"] == []
    assert guidance["show_secondary_data"] is False
