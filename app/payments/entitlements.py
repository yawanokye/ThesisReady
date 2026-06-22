"""ProjectReady AI chapter pricing and entitlement rules.

Commercial model
----------------
* Free Starter: Chapter One only, up to five selected sections, no paid extras.
* Every paid purchase is tied to one project chapter.
* A paid chapter includes one initial draft, one revision, one compliance check,
  and one DOCX export.
* The displayed international prices are fixed in USD.
* African customers are routed to Paystack and charged in GHS. The GHS amount
  is configured in ``paystack_payments.py`` through Render environment values.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
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

CHAPTER_PLANS: Dict[str, Dict[str, Any]] = {
    "bachelors_chapter": {
        "name": "Bachelors Project",
        "description": "One undergraduate project chapter with guided academic drafting and checking.",
        "price_usd": 4.99,
        "levels": ["Bachelors"],
        "drafts": 1,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 1,
    },
    "masters_chapter": {
        "name": "Masters Dissertation / MPhil Thesis",
        "description": "One Masters or MPhil chapter with higher-depth academic drafting and checking.",
        "price_usd": 9.99,
        "levels": [
            "Non-Research Masters",
            "Research Masters (e.g. MPhil)",
            "Research Masters / MPhil",
            "MPhil",
        ],
        "drafts": 1,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 2,
    },
    "doctorate_chapter": {
        "name": "Professional Doctorate / PhD",
        "description": "One DBA, DEd, professional doctorate, or PhD chapter with advanced academic depth.",
        "price_usd": 19.99,
        "levels": [
            "Professional Doctorate (e.g. DBA, DEd)",
            "Professional Doctorate",
            "DBA",
            "DEd",
            "PhD",
        ],
        "drafts": 1,
        "revisions": 1,
        "compliance_checks": 1,
        "docx_exports": 1,
        "display_order": 3,
    },
}


def _normalise_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def normalise_email(email: str) -> str:
    return str(email or "").strip().lower()


def normalise_chapter_key(chapter_number: Any, chapter_title: str = "") -> str:
    """Return a stable chapter entitlement key.

    ProjectReady labels can change between templates and UI builds, so payment
    ownership is bound to the project ID and numeric chapter rather than title text.
    """
    try:
        number = int(chapter_number)
    except Exception as exc:
        raise ValueError("chapter_number must be a positive integer") from exc
    if number < 1:
        raise ValueError("chapter_number must be a positive integer")
    return f"chapter-{number}"


def ordered_plans() -> List[Tuple[str, Dict[str, Any]]]:
    return sorted(CHAPTER_PLANS.items(), key=lambda item: item[1].get("display_order", 999))


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


def plan_key_for_level(level: str) -> str:
    target = _normalise_text(level)
    if not target:
        raise ValueError("Academic level is required.")

    # Exact and near-exact configured values first.
    for key, plan in ordered_plans():
        for configured_level in plan.get("levels", []):
            if target == _normalise_text(configured_level):
                return key

    # Tolerant matching for values sent by older ProjectReady UI builds.
    if "bachelor" in target or "undergraduate" in target:
        return "bachelors_chapter"
    if any(token in target for token in ("phd", "doctorate", "dba", "ded")):
        return "doctorate_chapter"
    if any(token in target for token in ("master", "mphil")):
        return "masters_chapter"

    raise ValueError(f"No paid chapter plan is configured for academic level: {level}")


def validate_plan_for_level(plan_key: str, level: str) -> Dict[str, Any]:
    expected = plan_key_for_level(level)
    supplied = str(plan_key or "").strip().lower()
    if supplied != expected:
        return {
            "allowed": False,
            "reason": "plan_level_mismatch",
            "message": "The selected plan does not match the academic level.",
            "recommended_plan": expected,
        }
    return {
        "allowed": True,
        "reason": "plan_matches_level",
        "message": "The selected plan matches the academic level.",
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


def build_plans_payload(level: str = "") -> Dict[str, Any]:
    recommended: Optional[str] = None
    if str(level or "").strip():
        try:
            recommended = plan_key_for_level(level)
        except ValueError:
            recommended = None

    plans: List[Dict[str, Any]] = []
    for key, _ in ordered_plans():
        plan = get_plan(key)
        plans.append(
            {
                "plan_key": key,
                "name": plan["name"],
                "description": plan["description"],
                "levels": plan["levels"],
                "amount": plan["amount"],
                "currency": plan["currency"],
                "price_display": plan["price_display"],
                "per": "chapter",
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
        "billing_model": "one-off per chapter",
        "display_currency": DEFAULT_DISPLAY_CURRENCY,
        "recommended_plan": recommended,
        "free_starter": {
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
    """Apply the Free Starter limit without depending on template-specific IDs."""
    try:
        number = int(chapter_number)
    except Exception:
        number = 0
    selected = [str(item).strip() for item in (selected_section_ids or []) if str(item).strip()]

    if revision_mode:
        return {
            "allowed": False,
            "reason": "revision_requires_paid_chapter",
            "message": "Chapter revision is included after purchasing the chapter plan.",
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
            "message": (
                f"Free Starter allows up to {FREE_CHAPTER_ONE_SECTION_LIMIT} selected "
                "sections of Chapter One."
            ),
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
