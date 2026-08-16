from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_user_guide_route_embeds_supplied_video_without_autoplay():
    client = TestClient(app)
    response = client.get("/user-guide")
    assert response.status_code == 200
    assert "youtube-nocookie.com/embed/NUwRzVqKKD4" in response.text
    assert "autoplay=1" not in response.text
    assert 'loading="lazy"' in response.text


def test_user_guide_reflects_complete_research_journey_architecture():
    html = (STATIC / "user_guide.html").read_text(encoding="utf-8")
    for text in [
        "Research Journey: 12 guided stages",
        "My Research Record",
        "Research Decision Checkpoints",
        "Claim Support Review",
        "Quick Chapter Development",
        "Review &amp; Strengthen",
        "Data &amp; Analysis Workspace",
        "Research Coach",
        "My Research Projects",
        "Final Research Audit",
        "Conceptual framework is optional.",
    ]:
        assert text in html
    assert "up to 50 selected papers" in html
    assert "No source, no citation." in html


def test_user_guide_alias_and_updated_pdf_are_available():
    client = TestClient(app)
    alias = client.get("/how-to-use")
    pdf = client.get("/static/guides/projectready-ai-annotated-user-guide.pdf")
    assert alias.status_code == 200
    assert pdf.status_code == 200
    assert pdf.headers.get("content-type", "").startswith("application/pdf")
    assert len(pdf.content) > 30_000


def test_current_modules_surface_contextual_guide_banner():
    expectations = {
        "topic_ideas.html": "topic-ideas",
        "workspace.html": "thesis-workspace",
        "chapter_strengthener.html": "chapter-strengthener",
        "research_coach.html": "research-coach",
        "my_projects.html": "my-projects",
        "data_analysis.html": "data-analysis",
    }
    for filename, module in expectations.items():
        html = (STATIC / filename).read_text(encoding="utf-8")
        assert f'data-guide-module="{module}"' in html
        assert 'href="/user-guide"' in html
        assert "user_guide_shared.css?v=20260816-guide-v3" in html
        assert "guide_banner.js?v=20260816-guide-v3" in html


def test_first_visit_banner_covers_new_modules_and_stores_only_dismissal_state():
    js = (STATIC / "guide_banner.js").read_text(encoding="utf-8")
    for module in ["topic-ideas", "thesis-workspace", "chapter-strengthener", "research-coach", "my-projects", "data-analysis"]:
        assert f'"{module}"' in js
    assert "projectready-guide-banner-dismissed:" in js
    assert 'localStorage.setItem(storageKey, "1")' in js
    assert "researchArea" not in js
    assert "projectId" not in js
    assert "chapterText" not in js


def test_legacy_guide_anchors_are_preserved_for_existing_links():
    html = (STATIC / "user_guide.html").read_text(encoding="utf-8")
    assert 'id="thesis-workspace"' in html
    assert 'id="chapter-strengthener"' in html
    assert 'id="topic-ideas"' not in html  # old topic page link now routes to current architecture overview
