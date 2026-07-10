from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"

REQUIRED_SUBPAGE_TABS = [
    'href="/"',
    'href="/#how-it-works"',
    'href="/#features"',
    'href="/#formats"',
    'href="/topic-ideas"',
    'href="/workspace"',
    'href="/chapter-strengthener"',
]


def read_static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_workspace_topic_and_strengthener_have_full_navigation_tabs():
    for filename in ["workspace.html", "topic_ideas.html", "chapter_strengthener.html"]:
        html = read_static(filename)
        for tab in REQUIRED_SUBPAGE_TABS:
            assert tab in html, f"{tab} missing from {filename}"


def test_homepage_keeps_full_navigation_tabs():
    html = read_static("index.html")
    for tab in [
        'href="/"',
        'href="#how-it-works"',
        'href="#features"',
        'href="#formats"',
        'href="/topic-ideas"',
        'href="/workspace"',
        'href="/chapter-strengthener"',
        'href="#pricing"',
        'href="#integrity"',
    ]:
        assert tab in html


def test_workspace_hero_is_plain_not_blue_gradient():
    css = read_static("workspace-ui-clarity.css")
    assert "body.workspace-clarity-theme > .hero" in css
    assert "background: #ffffff" in css
    assert "linear-gradient(135deg, #101828, #263bff)" not in css


def test_workspace_and_topic_use_strengthener_heading_rhythm():
    workspace_css = read_static("workspace-ui-clarity.css")
    topic_css = read_static("topic_ideas.css")
    for css in [workspace_css, topic_css]:
        assert "line-height: 1.02" in css
        assert "letter-spacing: -0.045em" in css


def test_homepage_hero_heading_matches_strengthener_rhythm():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    landing_css = (root / "app/static/landing.css").read_text()
    suite_css = (root / "app/static/projectready-suite.css").read_text()
    assert ".landing-suite .hero-copy h1" in landing_css
    assert ".landing-suite .hero-copy h1" in suite_css
    assert "line-height: 1.02" in landing_css
    assert "letter-spacing: -0.045em" in landing_css
    assert "line-height: 1.02 !important" in suite_css
    assert "letter-spacing: -0.045em !important" in suite_css
