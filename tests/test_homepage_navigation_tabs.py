from pathlib import Path


def test_homepage_navigation_has_required_tabs():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    required_links = {
        "How it works": '#how-it-works',
        "Core features": '#features',
        "Flexible formats": '#formats',
    }
    for label, href in required_links.items():
        assert f'href="{href}"' in html
        assert f'>{label}</a>' in html


def test_homepage_required_sections_exist():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    for section_id in ["how-it-works", "features", "formats"]:
        assert f'id="{section_id}"' in html
