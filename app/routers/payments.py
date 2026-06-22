"""FastAPI routes for ProjectReady AI chapter checkout and payment callbacks."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.payments.entitlements import (
    build_plans_payload,
    get_plan,
    get_price,
    plan_key_for_level,
    validate_plan_for_level,
)
from app.payments.router import choose_payment_provider, normalise_country_code
from app.payments.store import (
    create_pending_purchase,
    entitlement_status,
    init_payment_tables,
    make_provider_reference,
)
from app.payments.paystack import (
    PaystackError,
    get_paystack_charge,
    handle_paystack_webhook,
    initialize_paystack_payment,
    verify_and_activate_purchase,
)
from app.database import get_conn, row_to_dict
from app.template_store import get_chapter
from app.payments.stripe_provider import (
    StripePaymentError,
    handle_stripe_webhook,
    initialize_stripe_payment,
    verify_and_activate_stripe_session,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SUCCESS_PATH = os.environ.get("PROJECTREADY_PAYMENT_SUCCESS_PATH", "/workspace").strip() or "/workspace"
CANCEL_PATH = os.environ.get("PROJECTREADY_PAYMENT_CANCEL_PATH", "/workspace").strip() or "/workspace"

api_router = APIRouter(tags=["ProjectReady payments"])


class CheckoutRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    billing_country: str = Field(min_length=2, max_length=2)
    academic_level: str = Field(min_length=2, max_length=120)
    project_id: str = Field(min_length=1, max_length=120)
    chapter_number: int = Field(ge=1, le=99)
    chapter_title: str = Field(default="", max_length=200)
    plan_key: Optional[str] = Field(default=None, max_length=60)


class EntitlementStatusRequest(BaseModel):
    purchase_id: str = Field(min_length=10, max_length=100)
    access_token: str = Field(min_length=20, max_length=200)


def _valid_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@") or "." not in value.split("@", 1)[1]:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return value



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
        return str(profile.get("other_chapter_title") or supplied or "Other Chapter").strip()
    try:
        chapter = get_chapter(chapter_number)
        return str(chapter.get("chapter_title") or supplied or f"Chapter {chapter_number}").strip()
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Chapter {chapter_number} is not available in this workspace.") from exc

def _redirect(path: str, **params: Any) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{separator}{urlencode(params)}", status_code=303)


@api_router.get("/api/payments/plans")
def payment_plans(level: str = "") -> Dict[str, Any]:
    payload = build_plans_payload(level)
    for plan in payload.get("paid_plans", []):
        try:
            charge = get_paystack_charge(str(plan.get("plan_key") or ""))
            plan["paystack_amount"] = charge["amount"]
            plan["paystack_currency"] = charge["currency"]
            plan["paystack_price_display"] = charge["charged_display"]
        except Exception:
            # Keep the public USD display available even when Paystack is not
            # configured yet. Checkout will return the detailed configuration error.
            plan["paystack_price_display"] = None
    return payload


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
            detail="The selected academic level no longer matches the saved project. Recreate or refresh the project profile.",
        )

    try:
        country = normalise_country_code(payload.billing_country)
        recommended_plan = plan_key_for_level(stored_level)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chapter_title = _server_chapter_title(project, payload.chapter_number, payload.chapter_title)
    plan_key = str(payload.plan_key or recommended_plan).strip().lower()
    level_check = validate_plan_for_level(plan_key, stored_level)
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

    return {
        **checkout,
        "billing_country": country,
        "plan": {
            "plan_key": plan_key,
            "name": plan["name"],
            "price_display": plan["price_display"],
            "per": "chapter",
            "includes": {
                "initial_draft": 1,
                "revision": 1,
                "compliance_check": 1,
                "docx_export": 1,
            },
        },
        "message": "Checkout created. Store the returned purchase ID and access token before redirecting.",
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
        SUCCESS_PATH,
        payment="success",
        provider="paystack",
        purchase_id=purchase.get("id", ""),
        project_id=purchase.get("project_id", ""),
        chapter=purchase.get("chapter_number", ""),
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
        SUCCESS_PATH,
        payment="success",
        provider="stripe",
        purchase_id=purchase.get("id", ""),
        project_id=purchase.get("project_id", ""),
        chapter=purchase.get("chapter_number", ""),
    )


@api_router.post("/payment/stripe/webhook")
async def stripe_webhook(request: Request):
    # Signature verification requires the exact, unparsed request body.
    raw_body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        result = handle_stripe_webhook(
            raw_body=raw_body,
            signature=signature,
            database_url=DATABASE_URL,
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "message": str(exc)})
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
    """One-call integration for the existing ProjectReady FastAPI app."""
    init_payment_tables(DATABASE_URL)
    app.include_router(api_router)
