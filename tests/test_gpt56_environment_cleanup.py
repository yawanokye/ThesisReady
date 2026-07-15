from pathlib import Path

from app.ai_service import _select_draft_model
from app.chapter_revision_service import _revision_model
from app.topic_ideas_service import _select_topic_model, _topic_provider


def _clear_model_env(monkeypatch):
    names = [
        "OPENAI_MODEL", "OPENAI_BACHELOR_DRAFT_MODEL", "OPENAI_BACHELOR_CORE_MODEL",
        "OPENAI_NONRESEARCH_MASTERS_DRAFT_MODEL", "OPENAI_NONRESEARCH_MASTERS_CORE_MODEL",
        "OPENAI_RESEARCH_MASTERS_DRAFT_MODEL", "OPENAI_DOCTORAL_DRAFT_MODEL",
        "OPENAI_CHAPTER_REVISION_MODEL", "OPENAI_CHAPTER_REVISION_BACHELOR_MODEL",
        "OPENAI_CHAPTER_REVISION_MASTERS_MODEL", "OPENAI_CHAPTER_REVISION_RESEARCH_MODEL",
        "OPENAI_CHAPTER_REVISION_DOCTORAL_MODEL", "OPENAI_TOPIC_IDEA_MODEL",
        "OPENAI_TOPIC_IDEA_RESEARCH_MODEL", "OPENAI_TOPIC_IDEA_DOCTORAL_MODEL",
        "PROJECTREADY_TOPIC_IDEA_PROVIDER",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_default_draft_routes_use_gpt56(monkeypatch):
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("PROJECTREADY_MODEL_ROUTING", "level_based")
    assert _select_draft_model({"level": "Bachelors"}, 1)[0] == "gpt-5.6-terra"
    assert _select_draft_model({"level": "Non-Research Masters"}, 2)[0] == "gpt-5.6-terra"
    assert _select_draft_model({"level": "MPhil"}, 2)[0] == "gpt-5.6-terra"
    assert _select_draft_model({"level": "PhD"}, 2)[0] == "gpt-5.6-sol"


def test_default_strengthener_routes_use_gpt56(monkeypatch):
    _clear_model_env(monkeypatch)
    assert _revision_model("Bachelors") == "gpt-5.6-terra"
    assert _revision_model("Research Masters / MPhil") == "gpt-5.6-terra"
    assert _revision_model("PhD") == "gpt-5.6-sol"


def test_topic_ideas_default_to_openai_gpt56(monkeypatch):
    _clear_model_env(monkeypatch)
    assert _topic_provider() == "openai"
    assert _select_topic_model("Bachelors", "openai") == "gpt-5.6-luna"
    assert _select_topic_model("MPhil", "openai") == "gpt-5.6-terra"
    assert _select_topic_model("PhD", "openai") == "gpt-5.6-terra"


def test_active_environment_examples_contain_no_legacy_models():
    for filename in [
        ".env.example", ".env.projectready-model-router.example",
        ".env.production.web.example", ".env.production.worker.example",
    ]:
        text = Path(filename).read_text(encoding="utf-8")
        assert "gpt-5.5" not in text
        assert "gpt-5.4" not in text
        assert "gpt-4.1" not in text
        assert "PROJECTREADY_STRIPE_MODE" not in text
        assert "STRIPE_TEST_SECRET_KEY" not in text
