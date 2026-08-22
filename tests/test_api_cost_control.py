from types import SimpleNamespace

from app import ai_service
from app.ai_usage import start_usage_tracking, finish_usage_tracking
from app.routers import jobs as jobs_router


class _Responses:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(
            input_tokens=1000,
            output_tokens=500,
            input_tokens_details=SimpleNamespace(cached_tokens=200, cache_write_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=120),
        )
        return SimpleNamespace(output_text="ok", usage=usage)


class _Client:
    def __init__(self):
        self.responses = _Responses()


def test_openai_wrapper_forces_standard_tier_low_reasoning_and_tracks_usage(monkeypatch):
    monkeypatch.delenv("PROJECTREADY_OPENAI_SERVICE_TIER", raising=False)
    monkeypatch.delenv("PROJECTREADY_OPENAI_REASONING_EFFORT", raising=False)
    client = _Client()
    start_usage_tracking(job_type="chapter_draft", project_id="p1", chapter_number=2)
    text = ai_service._call_openai_response_safely(
        client, "gpt-5.6-terra", "instructions", "prompt", max_output_tokens=1200, purpose="test"
    )
    usage = finish_usage_tracking()
    assert text == "ok"
    assert client.responses.kwargs["service_tier"] == "default"
    assert client.responses.kwargs["reasoning"] == {"effort": "low"}
    assert usage["call_count"] == 1
    assert usage["reasoning_tokens"] == 120
    assert usage["estimated_cost_usd"] > 0


def test_stale_job_attempt_setting_is_ignored_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("PROJECTREADY_JOB_MAX_ATTEMPTS", "4")
    monkeypatch.delenv("PROJECTREADY_ALLOW_JOB_RETRIES", raising=False)
    assert jobs_router._max_attempts() == 1
    monkeypatch.setenv("PROJECTREADY_ALLOW_JOB_RETRIES", "1")
    assert jobs_router._max_attempts() == 4


def test_cross_model_fallback_is_disabled_by_default(monkeypatch):
    class FailingResponses:
        def __init__(self):
            self.calls = []
        def create(self, **kwargs):
            self.calls.append(kwargs.get("model"))
            raise RuntimeError("timeout")
    client = SimpleNamespace(responses=FailingResponses())
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-5.6-sol")
    monkeypatch.delenv("PROJECTREADY_ALLOW_FALLBACK_MODEL", raising=False)
    out = ai_service._call_openai_response_safely(client, "gpt-5.6-terra", "i", "p", max_output_tokens=5000)
    assert out == ""
    assert client.responses.calls == ["gpt-5.6-terra"]


def test_ai_long_chapter_planner_is_local_by_default(monkeypatch):
    class ExplodingResponses:
        def create(self, **kwargs):
            raise AssertionError("model planner should not run by default")
    client = SimpleNamespace(responses=ExplodingResponses())
    monkeypatch.delenv("PROJECTREADY_LONG_CHAPTER_AI_PLAN", raising=False)
    result = ai_service._build_long_chapter_plan(
        client=client,
        model="gpt-5.6-terra",
        instructions="x",
        base_prompt={"chapter":{"chapter_number":2,"chapter_title":"Literature Review"},"selected_sections":[]},
        full_req={"target_page_range":"60-70","target_words":22000},
        chunks=[[{"section_title":"Conceptual Review"}], [{"section_title":"Empirical Review"}]],
    )
    assert "Long-chapter development plan" in result
