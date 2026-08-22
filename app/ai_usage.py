from __future__ import annotations

import contextvars
import os
from typing import Any

_USAGE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("projectready_ai_usage", default=None)


def _truthy(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def _rate(model: str, kind: str) -> float:
    """USD per 1M tokens. Env overrides keep pricing maintainable."""
    m = str(model or "").lower()
    if "gpt-5.6-sol" in m or m == "gpt-5.6":
        defaults = {"input": 5.0, "cached": 0.5, "write": 6.25, "output": 30.0}
        prefix = "OPENAI_COST_SOL"
    elif "gpt-5.6-luna" in m:
        defaults = {"input": 0.20, "cached": 0.02, "write": 0.25, "output": 1.20}
        prefix = "OPENAI_COST_LUNA"
    else:
        defaults = {"input": 2.0, "cached": 0.20, "write": 2.50, "output": 12.0}
        prefix = "OPENAI_COST_TERRA"
    env_name = f"{prefix}_{kind.upper()}_PER_M"
    try:
        return float(os.getenv(env_name, str(defaults[kind])) or defaults[kind])
    except Exception:
        return defaults[kind]


def start_usage_tracking(*, job_type: str = "", project_id: str = "", chapter_number: int | None = None) -> None:
    _USAGE.set({
        "job_type": str(job_type or ""),
        "project_id": str(project_id or ""),
        "chapter_number": int(chapter_number or 0),
        "calls": [],
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "estimated_cost_usd": 0.0,
        "failed_attempts": [],
    })


def current_usage() -> dict[str, Any]:
    value = _USAGE.get()
    return dict(value or {})


def record_openai_response(response: Any, model: str, *, purpose: str = "model_call") -> None:
    ledger = _USAGE.get()
    if ledger is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    cached = int(getattr(input_details, "cached_tokens", 0) or 0) if input_details is not None else 0
    cache_write = int(getattr(input_details, "cache_write_tokens", 0) or 0) if input_details is not None else 0
    reasoning = int(getattr(output_details, "reasoning_tokens", 0) or 0) if output_details is not None else 0
    uncached = max(0, input_tokens - cached - cache_write)
    service_tier = str(getattr(response, "service_tier", "") or "").lower()
    tier_multiplier = 2.0 if service_tier in {"priority", "fast"} else 1.0
    cost = tier_multiplier * (
        uncached * _rate(model, "input")
        + cached * _rate(model, "cached")
        + cache_write * _rate(model, "write")
        + output_tokens * _rate(model, "output")
    ) / 1_000_000.0
    call = {
        "purpose": str(purpose or "model_call"),
        "model": str(model or ""),
        "service_tier": service_tier,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "cache_write_tokens": cache_write,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "estimated_cost_usd": round(cost, 6),
    }
    ledger["calls"].append(call)
    for key, amount in (
        ("input_tokens", input_tokens),
        ("cached_input_tokens", cached),
        ("cache_write_tokens", cache_write),
        ("output_tokens", output_tokens),
        ("reasoning_tokens", reasoning),
    ):
        ledger[key] = int(ledger.get(key, 0) or 0) + amount
    ledger["estimated_cost_usd"] = round(float(ledger.get("estimated_cost_usd", 0.0) or 0.0) + cost, 6)
    _USAGE.set(ledger)



def record_openai_failure(model: str, *, purpose: str = "model_call", error: str = "") -> None:
    """Record an API attempt that failed before usage metadata was returned.

    A timed-out request may still have consumed billable tokens at the provider.
    We therefore surface the failed attempt without pretending its exact cost is
    known locally.
    """
    ledger = _USAGE.get()
    if ledger is None:
        return
    failures = list(ledger.get("failed_attempts") or [])
    failures.append({
        "purpose": str(purpose or "model_call"),
        "model": str(model or ""),
        "error": str(error or "")[:240],
        "usage_unknown": True,
    })
    ledger["failed_attempts"] = failures
    _USAGE.set(ledger)

def finish_usage_tracking() -> dict[str, Any]:
    ledger = _USAGE.get() or {}
    result = dict(ledger)
    result["call_count"] = len(result.get("calls") or [])
    result["failed_attempt_count"] = len(result.get("failed_attempts") or [])
    result["estimated_cost_usd"] = round(float(result.get("estimated_cost_usd", 0.0) or 0.0), 4)
    _USAGE.set(None)
    return result


def optional_pass_budget_exceeded(default_usd: float = 2.0) -> bool:
    ledger = _USAGE.get() or {}
    try:
        cap = float(os.getenv("PROJECTREADY_OPTIONAL_AI_PASS_BUDGET_USD", str(default_usd)) or default_usd)
    except Exception:
        cap = default_usd
    return cap > 0 and float(ledger.get("estimated_cost_usd", 0.0) or 0.0) >= cap
