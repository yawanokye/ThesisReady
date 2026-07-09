"""FastAPI routes for ProjectReady AI chapter and revision-only checkout."""
from __future__ import annotations

import hmac
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
from app.payments.router import (
    choose_payment_provider,
    normalise_country_code,
)
from app.payments.store import (
    create_access_handoff,
    create_pending_purchase,
    entitlement_status,
    find_purchases_for_recovery,
    get_purchase,
    init_payment_tables,
    make_provider_reference,
    redeem_access_handoff,
    record_recovery_audit,
    rotate_access_token,
    verify_access_token,
)
from app.payments.stripe_provider import (
    StripePaymentError,
    handle_stripe_webhook,
    initialize_stripe_payment,
    stripe_environment_payload,
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


class TopicIdeasHandoffRequest(BaseModel):
    handoff: str = Field(min_length=20, max_length=300)


class TopicIdeasRecoveryRequest(BaseModel):
    purchase_id: str = Field(min_length=10, max_length=100)
    email: str = Field(min_length=5, max_length=254)


class PaidAccessRecoveryRequest(BaseModel):
    purchase_id: str = Field(min_length=10, max_length=100)
    email: str = Field(min_length=5, max_length=254)


class PaymentRecoveryRedeemRequest(BaseModel):
    handoff: str = Field(min_length=20, max_length=300)


class SupportRecoverySearchRequest(BaseModel):
    support_key: str = Field(min_length=8, max_length=300)
    email: str = Field(min_length=5, max_length=254)
    payment_identifier: str = Field(default="", max_length=200)


class SupportRecoveryCreateRequest(BaseModel):
    support_key: str = Field(min_length=8, max_length=300)
    email: str = Field(min_length=5, max_length=254)
    purchase_id: str = Field(min_length=10, max_length=100)
    operator_note: str = Field(default="", max_length=500)


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


def _configured_support_recovery_key() -> str:
    return os.environ.get("PROJECTREADY_SUPPORT_RECOVERY_KEY", "").strip()


def _require_support_recovery_key(supplied: str) -> None:
    configured = _configured_support_recovery_key()
    if not configured:
        raise HTTPException(status_code=503, detail="Payment support recovery is not configured.")
    if len(configured) < 16:
        raise HTTPException(status_code=503, detail="PROJECTREADY_SUPPORT_RECOVERY_KEY must contain at least 16 characters.")
    if not hmac.compare_digest(str(supplied or "").encode("utf-8"), configured.encode("utf-8")):
        raise HTTPException(status_code=403, detail="The payment support recovery key is invalid.")


def _purchase_product_area(purchase: Dict[str, Any]) -> str:
    metadata = purchase.get("metadata_json") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    if _is_topic_ideas_purchase(purchase):
        return "topic_ideas"
    mode = str(metadata.get("purchase_mode") or "chapter").strip().lower()
    return "chapter_strengthener" if mode == "revision_only" else "thesis_workspace"


def _verify_pending_purchase(purchase: Dict[str, Any]) -> Dict[str, Any]:
    if str(purchase.get("status") or "").lower() in {"paid", "active"}:
        return purchase
    provider = str(purchase.get("payment_provider") or "").lower()
    if provider == "stripe":
        session_id = str(purchase.get("checkout_session_id") or "").strip()
        if not session_id:
            return purchase
        result = verify_and_activate_stripe_session(session_id, database_url=DATABASE_URL)
    elif provider == "paystack":
        reference = str(purchase.get("provider_reference") or "").strip()
        if not reference:
            return purchase
        result = verify_and_activate_purchase(reference, database_url=DATABASE_URL)
    else:
        return purchase
    return (result.get("purchase") or purchase) if result.get("ok") else purchase


def _recovery_purchase_payload(purchase: Dict[str, Any]) -> Dict[str, Any]:
    metadata = purchase.get("metadata_json") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "purchase_id": purchase.get("id"),
        "payment_provider": purchase.get("payment_provider"),
        "provider_reference": purchase.get("provider_reference"),
        "checkout_session_id": purchase.get("checkout_session_id"),
        "product_area": _purchase_product_area(purchase),
        "project_id": purchase.get("project_id"),
        "chapter_number": purchase.get("chapter_number"),
        "chapter_title": purchase.get("chapter_title"),
        "plan_key": purchase.get("plan_key"),
        "amount": float(purchase.get("amount") or 0),
        "currency": purchase.get("currency"),
        "status": purchase.get("status"),
        "created_at": str(purchase.get("created_at") or ""),
        "paid_at": str(purchase.get("paid_at") or ""),
        "expires_at": str(purchase.get("expires_at") or ""),
        "return_path": _purchase_return_path(purchase, "/topic-ideas" if _is_topic_ideas_purchase(purchase) else SUCCESS_PATH),
        "remaining": {
            "draft": max(int(purchase.get("drafts_total") or 0) - int(purchase.get("drafts_used") or 0), 0),
            "revision": max(int(purchase.get("revisions_total") or 0) - int(purchase.get("revisions_used") or 0), 0),
            "compliance": max(int(purchase.get("compliance_total") or 0) - int(purchase.get("compliance_used") or 0), 0),
            "export": max(int(purchase.get("exports_total") or 0) - int(purchase.get("exports_used") or 0), 0),
        },
    }


def _is_topic_ideas_purchase(purchase: Dict[str, Any]) -> bool:
    metadata = purchase.get("metadata_json") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return (
        str(purchase.get("plan_key") or "").lower() == "topic_ideas_access"
        or str(metadata.get("purchase_mode") or "").lower() == "topic_ideas"
    )


def _successful_payment_redirect(purchase: Dict[str, Any], provider: str) -> RedirectResponse:
    metadata = purchase.get("metadata_json") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    params: Dict[str, Any] = {
        "payment": "success",
        "provider": provider,
        "purchase_id": purchase.get("id", ""),
        "project_id": purchase.get("project_id", ""),
        "chapter": purchase.get("chapter_number", ""),
        "mode": metadata.get("purchase_mode", "chapter"),
    }
    # Every paid product now receives a short-lived, single-use server handoff.
    # This restores the browser credential after payment even if localStorage was
    # cleared, blocked, or split across www/apex domains during the provider flow.
    try:
        params["handoff"] = create_access_handoff(
            str(purchase.get("id") or ""),
            purpose=f"{provider}_payment_return",
            database_url=DATABASE_URL,
        )
    except Exception:
        # Do not strand a paid customer on the provider callback. The return URL
        # still contains the Purchase ID, and /api/payments/recover-access can
        # verify the email and transaction before issuing a fresh credential.
        params["handoff_status"] = "recovery_required"
    return _redirect(_purchase_return_path(purchase), **params)


def _verify_pending_topic_purchase(purchase: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_topic_ideas_purchase(purchase):
        return purchase
    return _verify_pending_purchase(purchase)


@api_router.post("/api/admin/payment-recovery/search")
def search_payment_recovery(payload: SupportRecoverySearchRequest) -> Dict[str, Any]:
    """Search all ProjectReady payment products by exact customer email.

    This is a support-only endpoint. It never returns an access token. The
    optional identifier may be the internal Purchase ID, Paystack/ProjectReady
    reference, or Stripe Checkout Session ID.
    """
    _require_support_recovery_key(payload.support_key)
    email = _valid_email(payload.email)
    purchases = find_purchases_for_recovery(
        email,
        identifier=str(payload.payment_identifier or "").strip(),
        database_url=DATABASE_URL,
    )
    return {
        "ok": True,
        "email": email,
        "count": len(purchases),
        "purchases": [_recovery_purchase_payload(item) for item in purchases],
    }


@api_router.post("/api/admin/payment-recovery/create-link")
def create_payment_recovery_link(payload: SupportRecoveryCreateRequest, request: Request) -> Dict[str, Any]:
    """Create a short-lived, single-use recovery link for any paid product."""
    _require_support_recovery_key(payload.support_key)
    email = _valid_email(payload.email)
    purchase = get_purchase(payload.purchase_id, database_url=DATABASE_URL)
    if not purchase:
        raise HTTPException(status_code=404, detail="The selected purchase could not be found.")
    if str(purchase.get("user_email") or "").strip().lower() != email:
        raise HTTPException(status_code=403, detail="The customer email does not match this purchase.")
    try:
        purchase = _verify_pending_purchase(purchase)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Provider verification failed: {exc}") from exc
    if str(purchase.get("status") or "").lower() not in {"paid", "active"}:
        raise HTTPException(status_code=409, detail="The transaction is not yet verified as paid.")

    try:
        handoff = create_access_handoff(
            str(purchase.get("id") or ""),
            purpose="support_payment_recovery",
            ttl_minutes=60,
            database_url=DATABASE_URL,
        )
        record_recovery_audit(
            str(purchase.get("id") or ""),
            action="support_recovery_link_created",
            operator_note=payload.operator_note,
            database_url=DATABASE_URL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    configured_base = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    base_url = configured_base or str(request.base_url).rstrip("/")
    recovery_url = f"{base_url}/payment/recover?handoff={handoff}"
    return {
        "ok": True,
        "recovery_url": recovery_url,
        "expires_in_minutes": 60,
        "purchase": _recovery_purchase_payload(purchase),
        "message": "Send this one-time recovery link to the customer. It expires in 60 minutes and can be used once.",
    }


@api_router.post("/api/payments/redeem-recovery")
def redeem_payment_recovery(payload: PaymentRecoveryRedeemRequest) -> Dict[str, Any]:
    """Redeem a support-created handoff and issue a fresh product credential."""
    try:
        purchase = redeem_access_handoff(payload.handoff, database_url=DATABASE_URL)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_recovery_audit(
        str(purchase.get("id") or ""),
        action="support_recovery_link_redeemed",
        database_url=DATABASE_URL,
    )
    return {
        "ok": True,
        "purchase_id": purchase.get("id"),
        "access_token": purchase.get("access_token"),
        "provider": purchase.get("payment_provider"),
        "product_area": _purchase_product_area(purchase),
        "project_id": purchase.get("project_id"),
        "chapter_number": purchase.get("chapter_number"),
        "chapter_title": purchase.get("chapter_title"),
        "return_path": _purchase_return_path(purchase, "/topic-ideas" if _is_topic_ideas_purchase(purchase) else SUCCESS_PATH),
    }


@api_router.post("/api/payments/recover-access")
def recover_paid_access(payload: PaidAccessRecoveryRequest) -> Dict[str, Any]:
    """Restore a paid chapter/revision credential using the payment email and Purchase ID.

    This is the self-service backup for customers who completed payment but lost
    the browser token before using the remaining entitlements. The Purchase ID is
    shown on the payment-return URL and can also be supplied by support.
    """
    email = _valid_email(payload.email)
    purchase = get_purchase(payload.purchase_id, database_url=DATABASE_URL)
    if not purchase:
        raise HTTPException(status_code=404, detail="No paid access record matches that Purchase ID.")
    if str(purchase.get("user_email") or "").strip().lower() != email:
        raise HTTPException(status_code=403, detail="The payment email does not match this Purchase ID.")
    try:
        purchase = _verify_pending_purchase(purchase)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"The payment could not yet be verified: {exc}") from exc
    if str(purchase.get("status") or "").lower() not in {"paid", "active"}:
        raise HTTPException(status_code=409, detail="The payment is still pending or was not completed.")
    refreshed = rotate_access_token(str(purchase.get("id") or ""), database_url=DATABASE_URL)
    status = entitlement_status(
        str(refreshed.get("id") or ""),
        str(refreshed.get("access_token") or ""),
        database_url=DATABASE_URL,
    )
    return {
        "ok": True,
        "purchase_id": refreshed.get("id"),
        "access_token": refreshed.get("access_token"),
        "provider": refreshed.get("payment_provider"),
        "product_area": _purchase_product_area(refreshed),
        "project_id": refreshed.get("project_id"),
        "chapter_number": refreshed.get("chapter_number"),
        "chapter_title": refreshed.get("chapter_title"),
        "return_path": _purchase_return_path(refreshed, "/topic-ideas" if _is_topic_ideas_purchase(refreshed) else SUCCESS_PATH),
        "status": status,
        "message": "Paid access restored. Remaining entitlements are available on this device.",
    }


@api_router.get("/api/payments/environment")
def payment_environment() -> Dict[str, Any]:
    environment = stripe_environment_payload()
    environment.update({
        "provider_routing": "paystack_africa_stripe_elsewhere",
        "warning": "Live payment mode is active. African billing countries use Paystack and other countries use Stripe.",
    })
    return environment


@api_router.get("/api/payments/plans")
def payment_plans(level: str = "", mode: str = "chapter") -> Dict[str, Any]:
    payload = build_plans_payload(level, mode)
    payload["payment_environment"] = stripe_environment_payload()
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
    environment = stripe_environment_payload()
    return {
        "product": "ProjectReady AI Topic Ideas",
        "plan_key": "topic_ideas_access",
        "payment_environment": environment,
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
            "payment_environment": "live",
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


@api_router.post("/api/topic-ideas/redeem-handoff")
def redeem_topic_ideas_handoff(payload: TopicIdeasHandoffRequest) -> Dict[str, Any]:
    try:
        purchase = redeem_access_handoff(payload.handoff, database_url=DATABASE_URL)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not _is_topic_ideas_purchase(purchase):
        raise HTTPException(status_code=403, detail="This payment does not unlock Topic Ideas.")
    status = entitlement_status(
        str(purchase.get("id") or ""),
        str(purchase.get("access_token") or ""),
        database_url=DATABASE_URL,
    )
    return {
        "ok": True,
        "purchase_id": purchase.get("id"),
        "access_token": purchase.get("access_token"),
        "access_id": purchase.get("project_id"),
        "provider": purchase.get("payment_provider"),
        "status": status,
    }


@api_router.post("/api/topic-ideas/recover-access")
def recover_topic_ideas_access(payload: TopicIdeasRecoveryRequest) -> Dict[str, Any]:
    email = _valid_email(payload.email)
    purchase = get_purchase(payload.purchase_id, database_url=DATABASE_URL)
    if not purchase or not _is_topic_ideas_purchase(purchase):
        raise HTTPException(status_code=404, detail="No Topic Ideas payment matches those recovery details.")
    if str(purchase.get("user_email") or "").strip().lower() != email:
        raise HTTPException(status_code=403, detail="The payment email does not match this purchase.")
    try:
        purchase = _verify_pending_topic_purchase(purchase)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"The payment could not yet be verified: {exc}") from exc
    if str(purchase.get("status") or "").lower() not in {"paid", "active"}:
        raise HTTPException(status_code=409, detail="The payment is still pending or was not completed.")
    refreshed = rotate_access_token(str(purchase.get("id") or ""), database_url=DATABASE_URL)
    status = entitlement_status(
        str(refreshed.get("id") or ""),
        str(refreshed.get("access_token") or ""),
        database_url=DATABASE_URL,
    )
    return {
        "ok": True,
        "purchase_id": refreshed.get("id"),
        "access_token": refreshed.get("access_token"),
        "access_id": refreshed.get("project_id"),
        "provider": refreshed.get("payment_provider"),
        "status": status,
    }


@api_router.post("/api/topic-ideas/payment-status")
def topic_ideas_payment_status(payload: EntitlementStatusRequest) -> Dict[str, Any]:
    if not verify_access_token(payload.purchase_id, payload.access_token, database_url=DATABASE_URL):
        raise HTTPException(status_code=403, detail={"reason": "invalid_entitlement_token", "message": "The saved access credential is no longer valid."})
    purchase = get_purchase(payload.purchase_id, database_url=DATABASE_URL) or {}
    if not _is_topic_ideas_purchase(purchase):
        raise HTTPException(status_code=403, detail="This purchase does not unlock Topic Ideas.")
    verification_message = ""
    if str(purchase.get("status") or "").lower() not in {"paid", "active"}:
        try:
            purchase = _verify_pending_topic_purchase(purchase)
        except Exception as exc:
            verification_message = str(exc)[:240]
    result = entitlement_status(
        payload.purchase_id,
        payload.access_token,
        database_url=DATABASE_URL,
    )
    result["verification_message"] = verification_message
    result["payment_provider"] = purchase.get("payment_provider")
    return result


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
            "payment_environment": "live",
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
    return _successful_payment_redirect(purchase, "paystack")


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
    return _successful_payment_redirect(purchase, "stripe")


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
