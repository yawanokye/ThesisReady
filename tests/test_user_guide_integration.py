from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_user_guide_route_embeds_privacy_enhanced_video_without_autoplay():
    client = TestClient(app)
    response = client.get("/user-guide")
    assert response.status_code == 200
    assert "youtube-nocookie.com/embed/NUwRzVqKKD4" in response.text
    assert "autoplay=1" not in response.text
    assert 'loading="lazy"' in response.text
    assert 'id="topic-ideas"' in response.text
    assert 'id="thesis-workspace"' in response.text
    assert 'id="chapter-strengthener"' in response.text


def test_user_guide_alias_and_pdf_are_available():
    client = TestClient(app)
    alias = client.get("/how-to-use")
    pdf = client.get("/static/guides/projectready-ai-annotated-user-guide.pdf")
    assert alias.status_code == 200
    assert pdf.status_code == 200
    assert pdf.headers.get("content-type", "").startswith("application/pdf")
    assert len(pdf.content) > 1_000_000


def test_all_core_module_pages_link_to_contextual_user_guidance():
    module_expectations = {
        "topic_ideas.html": ("topic-ideas", "Read Topic Ideas guide"),
        "workspace.html": ("thesis-workspace", "Read Workspace guide"),
        "chapter_strengthener.html": ("chapter-strengthener", "Read Strengthener guide"),
    }
    for filename, (module_name, label) in module_expectations.items():
        html = (STATIC / filename).read_text(encoding="utf-8")
        assert f'data-guide-module="{module_name}"' in html
        assert 'href="/user-guide"' in html
        assert f'href="/user-guide#{module_name}"' in html
        assert label in html
        assert "user_guide_shared.css?v=20260719-user-guide-v1" in html
        assert "guide_banner.js?v=20260719-user-guide-v1" in html


def test_first_visit_banner_stores_only_dismissal_state():
    js = (STATIC / "guide_banner.js").read_text(encoding="utf-8")
    assert "projectready-guide-banner-dismissed:" in js
    assert "localStorage.setItem(storageKey, \"1\")" in js
    assert "researchArea" not in js
    assert "projectId" not in js
    assert "chapterText" not in js


def test_homepage_and_restricted_portal_surface_the_user_guide():
    homepage = (STATIC / "index.html").read_text(encoding="utf-8")
    portal = (ROOT / "app" / "internal_assets" / "portal.html").read_text(encoding="utf-8")
    assert "Watch the user guide" in homepage
    assert 'href="/user-guide"' in homepage
    assert 'href="/user-guide"' in portal


def test_annotated_infographic_is_embedded_as_html_viewer():
    client = TestClient(app)
    response = client.get("/user-guide")
    assert response.status_code == 200
    assert 'data-guide-viewer' in response.text
    assert response.text.count('data-guide-slide=') == 18
    assert response.text.count('data-guide-thumb=') == 18
    assert '/static/user_guide.js?v=20260719-user-guide-v2' in response.text
    assert '<object data="/static/guides/projectready-ai-annotated-user-guide.pdf' not in response.text


def test_all_annotated_html_page_images_and_thumbnails_are_available():
    client = TestClient(app)
    for page in range(1, 19):
        page_name = f"page-{page:02d}.webp"
        full = client.get(f"/static/guides/annotated-html/pages/{page_name}")
        thumb = client.get(f"/static/guides/annotated-html/thumbs/{page_name}")
        assert full.status_code == 200
        assert thumb.status_code == 200
        assert full.headers.get("content-type", "").startswith("image/webp")
        assert thumb.headers.get("content-type", "").startswith("image/webp")
        assert len(full.content) > 20_000
        assert len(thumb.content) > 3_000


def test_embedded_guide_script_supports_navigation_and_keyboard_controls():
    js = (STATIC / "user_guide.js").read_text(encoding="utf-8")
    assert "data-guide-prev" in js
    assert "data-guide-next" in js
    assert 'event.key === "ArrowLeft"' in js
    assert 'event.key === "ArrowRight"' in js
    assert "scrollIntoView" in js
