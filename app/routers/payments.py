"""FastAPI routes for ProjectReady AI chapter and revision-only checkout."""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator

from app.database import get_conn, row_to_dict
from app.payments.entitlements import (
    build_plans_payload,
    get_plan,
    get_price,
    normalise_purchase_mode,
    plan_key_for_level,
    validate_plan_for_level,
)
from app.payments.paystack import (
    PaystackError,
    get_paystack_charge,
    handle_paystack_webhook,
    initialize_paystack_payment,
    verify_and_activate_purchase,
)
from app.payments.router import choose_payment_provider, normalise_country_code
from app.payments.store import (
    create_pending_purchase,
    entitlement_status,
    init_payment_tables,
    make_provider_reference,
)
from app.payments.stripe_provider import (
    StripePaymentError,
    handle_stripe_webhook,
    initialize_stripe_payment,
    verify_and_activate_stripe_session,
)
from app.template_store import get_chapter

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SUCCESS_PATH = os.environ.get("PROJECTREADY_PAYMENT_SUCCESS_PATH", "/workspace").strip() or "/workspace"

api_router = APIRouter(tags=["ProjectReady payments"])


class CheckoutRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    billing_country: str = Field(min_length=2, max_length=2)
    academic_level: str = Field(min_length=2, max_length=120)
    project_id: str = Field(min_length=1, max_length=120)
    chapter_number: int = Field(ge=1, le=99)
    chapter_title: str = Field(default="", max_length=200)
    plan_key: Optional[str] = Field(default=None, max_length=60)
    purchase_mode: str = Field(default="chapter", max_length=40)
    return_path: str = Field(default="", max_length=500)

    @field_validator("purchase_mode")
    @classmethod
    def validate_purchase_mode(cls, value: str) -> str:
        return normalise_purchase_mode(value)


class EntitlementStatusRequest(BaseModel):
    purchase_id: str = Field(min_length=10, max_length=100)
    access_token: str = Field(min_length=20, max_length=200)


class TopicIdeasCheckoutRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    market: str = Field(default="ghana", max_length=20)
    return_path: str = Field(default="/topic-ideas", max_length=500)

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        market = str(value or "").strip().lower().replace("-", "_")
        if market in {"ghana", "gh"}:
            return "ghana"
        if market in {"international", "outside_ghana", "other", "global"}:
            return "international"
        raise ValueError("Choose Ghana or Outside Ghana.")


def _valid_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@") or "." not in value.split("@", 1)[1]:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return value


def _safe_return_path(path: str, fallback: str = SUCCESS_PATH) -> str:
    value = str(path or "").strip()
    if not value.startswith("/") or value.startswith("//"):
        return fallback
    if value.startswith("/payment/") or value.startswith("/api/"):
        return fallback
    return value[:500]


def _purchase_return_path(purchase: Dict[str, Any], fallback: str = SUCCESS_PATH) -> str:
    metadata = purchase.get("metadata_json") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return _safe_return_path(str(metadata.get("return_path") or ""), fallback)


def _load_project(project_id: str) -> Dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if not project:
        raise HTTPException(status_code=404, detail="Create the project before starting checkout.")
    return project


def _server_chapter_title(project: Dict[str, Any], chapter_number: int, supplied: str = "") -> str:
    profile = project.get("profile") or {}
    if chapter_number == 6:
        return str(
            profile.get("other_chapter_title")
            or profile.get("external_revision_chapter_title")
            or supplied
            or "Other Chapter"
        ).strip()
    try:
        chapter = get_chapter(chapter_number)
        return str(chapter.get("chapter_title") or supplied or f"Chapter {chapter_number}").strip()
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Chapter {chapter_number} is not available in this workspace.",
        ) from exc


def _redirect(path: str, **params: Any) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{separator}{urlencode(params)}", status_code=303)


@api_router.get("/api/payments/plans")
def payment_plans(level: str = "", mode: str = "chapter") -> Dict[str, Any]:
    payload = build_plans_payload(level, mode)
    for plan in payload.get("paid_plans", []):
        try:
            charge = get_paystack_charge(str(plan.get("plan_key") or ""))
            plan["paystack_amount"] = charge["amount"]
            plan["paystack_currency"] = charge["currency"]
            plan["paystack_price_display"] = charge["charged_display"]
        except Exception:
            plan["paystack_price_display"] = None
    return payload


@api_router.get("/api/topic-ideas/access-plan")
def topic_ideas_access_plan() -> Dict[str, Any]:
    plan = get_plan("topic_ideas_access")
    paystack_charge = get_paystack_charge("topic_ideas_access")
    return {
        "product": "ProjectReady AI Topic Ideas",
        "plan_key": "topic_ideas_access",
        "ghana": {
            "provider": "paystack",
            "amount": float(paystack_charge["amount"]),
            "currency": "GHS",
            "display": paystack_charge["charged_display"],
        },
        "international": {
            "provider": "stripe",
            "amount": float(plan["amount"]),
            "currency": "USD",
            "display": plan["price_display"],
        },
        "free_preview": {
            "ideas": 2,
            "payment_required": False,
        },
        "includes": {
            "topic_idea_generations": 1,
            "maximum_ideas": 12,
            "trend_grounding": True,
            "proposed_objectives": True,
            "data_and_instrument_source_suggestions": True,
        },
        "validity_days": int(plan["validity_days"]),
    }


@api_router.post("/api/topic-ideas/checkout")
def start_topic_ideas_checkout(payload: TopicIdeasCheckoutRequest) -> Dict[str, Any]:
    email = _valid_email(payload.email)
    plan_key = "topic_ideas_access"
    plan = get_plan(plan_key)
    display_price = get_price(plan_key)
    provider = "paystack" if payload.market == "ghana" else "stripe"
    provider_reference = make_provider_reference(provider)
    access_id = f"topic-ideas-{uuid.uuid4()}"
    return_path = _safe_return_path(payload.return_path, "/topic-ideas")

    if provider == "paystack":
        charge = get_paystack_charge(plan_key)
        charge_amount = float(charge["amount"])
        charge_currency = str(charge["currency"])
        pricing_metadata = charge
        billing_country = "GH"
    else:
        charge_amount = float(display_price["amount"])
        charge_currency = str(display_price["currency"])
        pricing_metadata = {
            "selected_amount": display_price["amount"],
            "selected_currency": display_price["currency"],
            "selected_display": display_price["display"],
            "amount": display_price["amount"],
            "currency": display_price["currency"],
            "charged_display": display_price["display"],
            "calculation": "fixed_usd_topic_ideas_price",
        }
        billing_country = "INTERNATIONAL"

    purchase = create_pending_purchase(
        user_email=email,
        project_id=access_id,
        chapter_number=99,
        chapter_title="Topic Ideas Access",
        academic_level="Topic Ideas",
        plan_key=plan_key,
        amount=charge_amount,
        currency=charge_currency,
        display_amount=float(display_price["amount"]),
        display_currency=str(display_price["currency"]),
        payment_provider=provider,
        provider_reference=provider_reference,
        metadata={
            "billing_country": billing_country,
            "billing_market": payload.market,
            "plan_name": plan["name"],
            "product_area": "topic_ideas",
            "purchase_mode": "topic_ideas",
            "return_path": return_path,
            "pricing": pricing_metadata,
        },
        database_url=DATABASE_URL,
    )

    try:
        checkout = (
            initialize_paystack_payment(purchase)
            if provider == "paystack"
            else initialize_stripe_payment(purchase, database_url=DATABASE_URL)
        )
    except (PaystackError, StripePaymentError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        **checkout,
        "access_id": access_id,
        "purchase_mode": "topic_ideas",
        "return_path": return_path,
        "plan": {
            "plan_key": plan_key,
            "name": plan["name"],
            "price_display": (
                pricing_metadata.get("charged_display")
                if provider == "paystack"
                else display_price["display"]
            ),
            "includes": {
                "topic_idea_generations": 1,
                "maximum_ideas": 12,
            },
            "validity_days": int(plan["validity_days"]),
        },
        "message": "Checkout created to unlock up to 12 ideas. This browser stores the access credential before redirecting to payment.",
    }


@api_router.post("/api/payments/checkout")
def start_checkout(payload: CheckoutRequest) -> Dict[str, Any]:
    email = _valid_email(payload.email)
    project = _load_project(payload.project_id)
    profile = project.get("profile") or {}
    stored_level = str(profile.get("level") or payload.academic_level or "").strip()
    if not stored_level:
        raise HTTPException(status_code=422, detail="The project academic level is missing.")
    if payload.academic_level.strip() and payload.academic_level.strip() != stored_level:
        raise HTTPException(
            status_code=409,
            detail="The selected academic level no longer matches the saved project. Refresh the project profile.",
        )

    purchase_mode = normalise_purchase_mode(payload.purchase_mode)
    try:
        country = normalise_country_code(payload.billing_country)
        recommended_plan = plan_key_for_level(stored_level, purchase_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chapter_title = _server_chapter_title(project, payload.chapter_number, payload.chapter_title)
    plan_key = str(payload.plan_key or recommended_plan).strip().lower()
    level_check = validate_plan_for_level(plan_key, stored_level, purchase_mode)
    if not level_check.get("allowed"):
        raise HTTPException(status_code=422, detail=level_check)

    plan = get_plan(plan_key)
    provider = choose_payment_provider(country)
    provider_reference = make_provider_reference(provider)
    display_price = get_price(plan_key)

    if provider == "paystack":
        try:
            charge = get_paystack_charge(plan_key)
        except PaystackError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        charge_amount = charge["amount"]
        charge_currency = charge["currency"]
        pricing_metadata = charge
    else:
        charge_amount = display_price["amount"]
        charge_currency = display_price["currency"]
        pricing_metadata = {
            "selected_amount": display_price["amount"],
            "selected_currency": display_price["currency"],
            "selected_display": display_price["display"],
            "amount": display_price["amount"],
            "currency": display_price["currency"],
            "charged_display": display_price["display"],
            "calculation": "fixed_usd_plan_price",
        }

    return_path = _safe_return_path(
        payload.return_path,
        "/chapter-strengthener" if purchase_mode == "revision_only" else SUCCESS_PATH,
    )
    purchase = create_pending_purchase(
        user_email=email,
        project_id=payload.project_id,
        chapter_number=payload.chapter_number,
        chapter_title=chapter_title,
        academic_level=stored_level,
        plan_key=plan_key,
        amount=float(charge_amount),
        currency=charge_currency,
        display_amount=float(display_price["amount"]),
        display_currency=display_price["currency"],
        payment_provider=provider,
        provider_reference=provider_reference,
        metadata={
            "billing_country": country,
            "plan_name": plan["name"],
            "project_title": project.get("title", ""),
            "purchase_mode": purchase_mode,
            "return_path": return_path,
            "pricing": pricing_metadata,
        },
        database_url=DATABASE_URL,
    )

    try:
        if provider == "paystack":
            checkout = initialize_paystack_payment(purchase)
        else:
            checkout = initialize_stripe_payment(purchase, database_url=DATABASE_URL)
    except (PaystackError, StripePaymentError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    includes = {
        "initial_draft": int(plan["drafts"]),
        "revision": int(plan["revisions"]),
        "compliance_check": int(plan["compliance_checks"]),
        "docx_export": int(plan["docx_exports"]),
    }
    return {
        **checkout,
        "billing_country": country,
        "purchase_mode": purchase_mode,
        "return_path": return_path,
        "plan": {
            "plan_key": plan_key,
            "name": plan["name"],
            "price_display": plan["price_display"],
            "per": (
                "topic-idea generation"
                if purchase_mode == "topic_ideas"
                else "uploaded chapter" if purchase_mode == "revision_only" else "chapter"
            ),
            "includes": includes,
        },
        "message": "Checkout created. The browser securely stores the returned access credential before redirecting.",
    }


@api_router.get("/payment/paystack/callback")
def paystack_callback(reference: str = "", trxref: str = ""):
    reference = reference or trxref
    if not reference:
        return _redirect(SUCCESS_PATH, payment="failed", reason="missing_reference")
    try:
        result = verify_and_activate_purchase(reference, database_url=DATABASE_URL)
    except Exception:
        return _redirect(SUCCESS_PATH, payment="failed", provider="paystack")
    if not result.get("ok"):
        return _redirect(SUCCESS_PATH, payment="failed", provider="paystack")
    purchase = result.get("purchase") or {}
    return _redirect(
        _purchase_return_path(purchase),
        payment="success",
        provider="paystack",
        purchase_id=purchase.get("id", ""),
        project_id=purchase.get("project_id", ""),
        chapter=purchase.get("chapter_number", ""),
        mode=(purchase.get("metadata_json") or {}).get("purchase_mode", "chapter"),
    )


@api_router.post("/payment/paystack/webhook")
async def paystack_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    try:
        result = handle_paystack_webhook(
            raw_body=raw_body,
            signature=signature,
            database_url=DATABASE_URL,
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "message": str(exc)})
    return JSONResponse(status_code=int(result.get("status_code", 200)), content=result)


@api_router.get("/payment/stripe/success")
def stripe_success(session_id: str = ""):
    if not session_id:
        return _redirect(SUCCESS_PATH, payment="failed", reason="missing_session")
    try:
        result = verify_and_activate_stripe_session(session_id, database_url=DATABASE_URL)
    except Exception:
        return _redirect(SUCCESS_PATH, payment="failed", provider="stripe")
    if not result.get("ok"):
        return _redirect(SUCCESS_PATH, payment="failed", provider="stripe")
    purchase = result.get("purchase") or {}
    return _redirect(
        _purchase_return_path(purchase),
        payment="success",
        provider="stripe",
        purchase_id=purchase.get("id", ""),
        project_id=purchase.get("project_id", ""),
        chapter=purchase.get("chapter_number", ""),
        mode=(purchase.get("metadata_json") or {}).get("purchase_mode", "chapter"),
    )


@api_router.post("/payment/stripe/webhook")
async def stripe_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        result = handle_stripe_webhook(
            raw_body=raw_body,
            signature=signature,
            database_url=DATABASE_URL,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "message": message,
                "stage": "stripe_webhook_activation",
            },
        )
    return JSONResponse(status_code=int(result.get("status_code", 200)), content=result)


@api_router.post("/api/payments/entitlement-status")
def get_entitlement_status(payload: EntitlementStatusRequest):
    result = entitlement_status(
        payload.purchase_id,
        payload.access_token,
        database_url=DATABASE_URL,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=403, detail=result)
    return result


def attach_payment_routes(app: Any) -> None:
    init_payment_tables(DATABASE_URL)
    app.include_router(api_router)
