"""ProjectReady AI pricing and entitlement rules.

Two purchase pathways are supported:
* Standard guided chapter package: one working draft, one strengthening revision, one compliance review and one editable DOCX export.
* Revision-only package: one strengthening revision, one compliance check and one DOCX export for a chapter brought from outside ProjectReady AI.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import os
import re

DEFAULT_DISPLAY_CURRENCY = "USD"
PURCHASE_VALIDITY_DAYS = 90
FREE_CHAPTER_NUMBER = 1
FREE_CHAPTER_ONE_SECTION_LIMIT = 5

ACTION_FIELDS: Dict[str, Tuple[str, str]] = {
    "draft": ("drafts_total", "drafts_used"),
    "revision": ("revisions_total", "revisions_used"),
    "compliance": ("compliance_total", "compliance_used"),
    "export": ("exports_total", "exports_used"),
}


def _price_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return round(max(value, 0.5), 2)


CHAPTER_PLANS: Dict[str, Dict[str, Any]] = {
    "bachelors_chapter": {
        "name": "Bachelors Project",
        "description": "Guided development of one undergraduate project chapter working draft, with strengthening and compliance review.",
        "price_usd": 4.99,
        "levels": ["Bachelors"],
        "purchase_mode": "chapter",
        "drafts": 1,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 1,
    },
    "masters_chapter": {
        "name": "Masters Dissertation / MPhil Thesis",
        "description": "Guided development of one Masters or MPhil chapter working draft, with higher-depth strengthening and compliance review.",
        "price_usd": 9.99,
        "levels": [
            "Non-Research Masters",
            "Research Masters (e.g. MPhil)",
            "Research Masters / MPhil",
            "MPhil",
        ],
        "purchase_mode": "chapter",
        "drafts": 1,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 2,
    },
    "doctorate_chapter": {
        "name": "Professional Doctorate / PhD",
        "description": "Guided development of one professional doctorate or PhD chapter working draft with advanced academic depth and review.",
        "price_usd": 19.99,
        "levels": [
            "Professional Doctorate (e.g. DBA, DEd)",
            "Professional Doctorate / DBA / DEd",
            "Professional Doctorate",
            "DBA",
            "DEd",
            "PhD",
        ],
        "purchase_mode": "chapter",
        "drafts": 1,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 3,
    },
    "bachelors_revision": {
        "name": "Bachelors Chapter Strengthening",
        "description": "Strengthen one existing undergraduate chapter brought from outside ProjectReady AI.",
        "price_usd": _price_env("PROJECTREADY_BACHELORS_REVISION_USD", 2.99),
        "levels": ["Bachelors"],
        "purchase_mode": "revision_only",
        "drafts": 0,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 11,
    },
    "masters_revision": {
        "name": "Masters / MPhil Chapter Strengthening",
        "description": "Strengthen one existing Masters or MPhil chapter brought from outside ProjectReady AI.",
        "price_usd": _price_env("PROJECTREADY_MASTERS_REVISION_USD", 5.99),
        "levels": [
            "Non-Research Masters",
            "Research Masters (e.g. MPhil)",
            "Research Masters / MPhil",
            "MPhil",
        ],
        "purchase_mode": "revision_only",
        "drafts": 0,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 12,
    },
    "doctorate_revision": {
        "name": "Doctoral Chapter Strengthening",
        "description": "Strengthen one existing professional doctorate or PhD chapter with advanced academic depth.",
        "price_usd": _price_env("PROJECTREADY_DOCTORATE_REVISION_USD", 11.99),
        "levels": [
            "Professional Doctorate (e.g. DBA, DEd)",
            "Professional Doctorate / DBA / DEd",
            "Professional Doctorate",
            "DBA",
            "DEd",
            "PhD",
        ],
        "purchase_mode": "revision_only",
        "drafts": 0,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 13,
    },
}


def _normalise_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def normalise_purchase_mode(value: str) -> str:
    mode = str(value or "chapter").strip().lower().replace("-", "_")
    return "revision_only" if mode in {"revision", "revision_only", "strengthening"} else "chapter"


def normalise_email(email: str) -> str:
    return str(email or "").strip().lower()


def normalise_chapter_key(chapter_number: Any, chapter_title: str = "") -> str:
    try:
        number = int(chapter_number)
    except Exception as exc:
        raise ValueError("chapter_number must be a positive integer") from exc
    if number < 1:
        raise ValueError("chapter_number must be a positive integer")
    return f"chapter-{number}"


def ordered_plans(purchase_mode: str | None = None) -> List[Tuple[str, Dict[str, Any]]]:
    mode = normalise_purchase_mode(purchase_mode or "chapter") if purchase_mode else None
    items = CHAPTER_PLANS.items()
    if mode:
        items = [item for item in items if item[1].get("purchase_mode", "chapter") == mode]
    return sorted(items, key=lambda item: item[1].get("display_order", 999))


def get_plan(plan_key: str) -> Dict[str, Any]:
    key = str(plan_key or "").strip().lower()
    plan = CHAPTER_PLANS.get(key)
    if not plan:
        raise ValueError(f"Unknown ProjectReady AI plan: {plan_key}")
    result = deepcopy(plan)
    result["plan_key"] = key
    result["currency"] = DEFAULT_DISPLAY_CURRENCY
    result["amount"] = float(result["price_usd"])
    result["price_display"] = f"US${result['price_usd']:.2f}"
    result["validity_days"] = PURCHASE_VALIDITY_DAYS
    return result


def plan_key_for_level(level: str, purchase_mode: str = "chapter") -> str:
    target = _normalise_text(level)
    mode = normalise_purchase_mode(purchase_mode)
    if not target:
        raise ValueError("Academic level is required.")

    for key, plan in ordered_plans(mode):
        for configured_level in plan.get("levels", []):
            if target == _normalise_text(configured_level):
                return key

    suffix = "revision" if mode == "revision_only" else "chapter"
    if "bachelor" in target or "undergraduate" in target:
        return f"bachelors_{suffix}"
    if any(token in target for token in ("phd", "doctorate", "dba", "ded")):
        return f"doctorate_{suffix}"
    if any(token in target for token in ("master", "mphil")):
        return f"masters_{suffix}"
    raise ValueError(f"No {mode.replace('_', ' ')} plan is configured for academic level: {level}")


def validate_plan_for_level(plan_key: str, level: str, purchase_mode: str = "chapter") -> Dict[str, Any]:
    expected = plan_key_for_level(level, purchase_mode)
    supplied = str(plan_key or "").strip().lower()
    if supplied != expected:
        return {
            "allowed": False,
            "reason": "plan_level_or_mode_mismatch",
            "message": "The selected plan does not match the academic level or purchase pathway.",
            "recommended_plan": expected,
        }
    return {
        "allowed": True,
        "reason": "plan_matches_level_and_mode",
        "message": "The selected plan matches the academic level and purchase pathway.",
        "recommended_plan": expected,
    }


def get_price(plan_key: str) -> Dict[str, Any]:
    plan = get_plan(plan_key)
    return {
        "amount": float(plan["price_usd"]),
        "currency": "USD",
        "display": f"US${float(plan['price_usd']):.2f}",
    }


def quota_payload(plan_key: str) -> Dict[str, int]:
    plan = get_plan(plan_key)
    return {
        "drafts_total": int(plan["drafts"]),
        "revisions_total": int(plan["revisions"]),
        "compliance_total": int(plan["compliance_checks"]),
        "exports_total": int(plan["docx_exports"]),
    }


def build_plans_payload(level: str = "", purchase_mode: str = "chapter") -> Dict[str, Any]:
    mode = normalise_purchase_mode(purchase_mode)
    recommended: Optional[str] = None
    if str(level or "").strip():
        try:
            recommended = plan_key_for_level(level, mode)
        except ValueError:
            recommended = None

    plans: List[Dict[str, Any]] = []
    for key, _ in ordered_plans(mode):
        plan = get_plan(key)
        plans.append(
            {
                "plan_key": key,
                "name": plan["name"],
                "description": plan["description"],
                "levels": plan["levels"],
                "purchase_mode": plan["purchase_mode"],
                "amount": plan["amount"],
                "currency": plan["currency"],
                "price_display": plan["price_display"],
                "per": "uploaded chapter" if mode == "revision_only" else "chapter",
                "includes": {
                    "initial_draft": plan["drafts"],
                    "revision": plan["revisions"],
                    "compliance_check": plan["compliance_checks"],
                    "docx_export": plan["docx_exports"],
                },
                "validity_days": plan["validity_days"],
                "recommended": key == recommended,
            }
        )

    return {
        "product": "ProjectReady AI",
        "billing_model": "one-off revision-only" if mode == "revision_only" else "one-off per chapter",
        "purchase_mode": mode,
        "display_currency": DEFAULT_DISPLAY_CURRENCY,
        "recommended_plan": recommended,
        "free_starter": None if mode == "revision_only" else {
            "price_display": "US$0",
            "chapter_number": FREE_CHAPTER_NUMBER,
            "maximum_selected_sections": FREE_CHAPTER_ONE_SECTION_LIMIT,
            "revision": False,
            "compliance_check": False,
            "docx_export": False,
        },
        "paid_plans": plans,
    }


def is_free_generation_allowed(
    *,
    chapter_number: Any,
    selected_section_ids: List[str] | Tuple[str, ...] | None,
    revision_mode: bool = False,
) -> Dict[str, Any]:
    try:
        number = int(chapter_number)
    except Exception:
        number = 0
    selected = [str(item).strip() for item in (selected_section_ids or []) if str(item).strip()]

    if revision_mode:
        return {
            "allowed": False,
            "reason": "revision_requires_paid_chapter",
            "message": "Chapter revision requires a paid chapter or revision-only plan.",
        }
    if number != FREE_CHAPTER_NUMBER:
        return {
            "allowed": False,
            "reason": "paid_chapter_required",
            "message": "Free Starter is limited to Chapter One.",
        }
    if len(selected) > FREE_CHAPTER_ONE_SECTION_LIMIT:
        return {
            "allowed": False,
            "reason": "free_section_limit_exceeded",
            "message": f"Free Starter allows up to {FREE_CHAPTER_ONE_SECTION_LIMIT} selected sections of Chapter One.",
        }
    if not selected:
        return {
            "allowed": False,
            "reason": "no_sections_selected",
            "message": "Select at least one Chapter One section.",
        }
    return {
        "allowed": True,
        "reason": "free_starter_allowed",
        "message": "This request is within the Free Starter limit.",
        "remaining_section_slots": FREE_CHAPTER_ONE_SECTION_LIMIT - len(selected),
    }


def expiry_datetime(days: int = PURCHASE_VALIDITY_DAYS) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=int(days))


def action_columns(action: str) -> Tuple[str, str]:
    key = str(action or "").strip().lower()
    if key not in ACTION_FIELDS:
        raise ValueError(f"Unsupported entitlement action: {action}")
    return ACTION_FIELDS[key]
