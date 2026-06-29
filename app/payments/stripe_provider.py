"""Stripe Checkout integration for non-African ProjectReady AI customers."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from app.payments.store import (
    activate_purchase,
    get_purchase_by_reference,
    record_event_once,
    set_checkout_session,
)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
CANCEL_PATH = os.environ.get("PROJECTREADY_PAYMENT_CANCEL_PATH", "/workspace").strip() or "/workspace"


class StripePaymentError(RuntimeError):
    pass


def _stripe_module():
    if not STRIPE_SECRET_KEY:
        raise StripePaymentError("STRIPE_SECRET_KEY is not configured.")
    try:
        import stripe
    except ImportError as exc:
        raise StripePaymentError("Install the Stripe SDK with: pip install stripe") from exc
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def amount_to_subunit(amount: float) -> int:
    return int(round(float(amount) * 100))


def initialize_stripe_payment(purchase: Dict[str, Any], *, database_url: str = "") -> Dict[str, Any]:
    stripe = _stripe_module()
    purchase_metadata = purchase.get("metadata_json") or {}
    if not isinstance(purchase_metadata, dict):
        purchase_metadata = {}
    purchase_mode = str(purchase_metadata.get("purchase_mode") or "chapter")
    return_path = str(purchase_metadata.get("return_path") or CANCEL_PATH)
    if not return_path.startswith("/") or return_path.startswith("//"):
        return_path = CANCEL_PATH
    description = (
        "One chapter strengthening revision, one compliance check, and one DOCX export."
        if purchase_mode == "revision_only"
        else "One chapter draft, one revision, one compliance check, and one DOCX export."
    )
    cancel_separator = "&" if "?" in return_path else "?"
    metadata = {
        "product": "ProjectReady AI",
        "purchase_id": purchase["id"],
        "provider_reference": purchase["provider_reference"],
        "project_id": purchase["project_id"],
        "chapter_key": purchase["chapter_key"],
        "chapter_number": str(purchase["chapter_number"]),
        "academic_level": purchase["academic_level"],
        "plan_key": purchase["plan_key"],
        "purchase_mode": purchase_mode,
    }
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            customer_email=purchase["user_email"],
            client_reference_id=purchase["id"],
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": str(purchase["currency"]).lower(),
                        "unit_amount": amount_to_subunit(float(purchase["amount"])),
                        "product_data": {
                            "name": f"ProjectReady AI, {purchase['chapter_title'] or purchase['chapter_key']}",
                            "description": description,
                        },
                    },
                }
            ],
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            success_url=f"{APP_BASE_URL}/payment/stripe/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_BASE_URL}{return_path}{cancel_separator}payment=cancelled&purchase_id={purchase['id']}",
            allow_promotion_codes=False,
        )
    except Exception as exc:
        raise StripePaymentError(f"Stripe checkout initialization failed: {exc}") from exc

    set_checkout_session(purchase["id"], session.id, database_url=database_url)
    return {
        "ok": True,
        "provider": "stripe",
        "checkout_url": session.url,
        "session_id": session.id,
        "provider_reference": purchase["provider_reference"],
        "purchase_id": purchase["id"],
        "amount": float(purchase["amount"]),
        "currency": purchase["currency"],
        "display_amount": float(purchase.get("display_amount") or purchase["amount"]),
        "display_currency": purchase.get("display_currency") or purchase["currency"],
        "access_token": purchase.get("access_token"),
    }


def _session_to_dict(session: Any) -> Dict[str, Any]:
    if hasattr(session, "to_dict_recursive"):
        return session.to_dict_recursive()
    return dict(session)


def verify_and_activate_stripe_session(session_id: str, *, database_url: str = "") -> Dict[str, Any]:
    stripe = _stripe_module()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise StripePaymentError(f"Stripe session verification failed: {exc}") from exc

    data = _session_to_dict(session)
    metadata = data.get("metadata") or {}
    reference = str(metadata.get("provider_reference") or "")
    if not reference:
        return {"ok": False, "activated": False, "message": "Stripe session has no ProjectReady reference."}

    purchase = get_purchase_by_reference(reference, database_url=database_url)
    if not purchase:
        return {"ok": False, "activated": False, "message": "No ProjectReady purchase matches this Stripe session."}

    if str(data.get("payment_status") or "").lower() != "paid":
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe has not marked this checkout as paid.",
            "payment_status": data.get("payment_status"),
        }

    amount_total = int(data.get("amount_total") or 0)
    expected_subunit = amount_to_subunit(float(purchase["amount"]))
    currency = str(data.get("currency") or "").upper()
    if amount_total != expected_subunit or currency != str(purchase["currency"]).upper():
        return {"ok": False, "activated": False, "message": "Stripe amount or currency does not match the chapter purchase."}

    customer_details = data.get("customer_details") or {}
    stripe_email = str(customer_details.get("email") or data.get("customer_email") or "").lower()
    if stripe_email and stripe_email != str(purchase["user_email"]).lower():
        return {"ok": False, "activated": False, "message": "Stripe customer email does not match the chapter purchase."}

    activated = activate_purchase(
        provider_reference=reference,
        verified_amount=amount_total / 100,
        verified_currency=currency,
        provider_payload=data,
        database_url=database_url,
    )
    return {"ok": True, "activated": True, "purchase": activated, "session": data}


def handle_stripe_webhook(
    *,
    raw_body: bytes,
    signature: str,
    database_url: str = "",
) -> Dict[str, Any]:
    if not STRIPE_WEBHOOK_SECRET:
        raise StripePaymentError("STRIPE_WEBHOOK_SECRET is not configured.")
    stripe = _stripe_module()
    try:
        event = stripe.Webhook.construct_event(raw_body, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        return {"ok": False, "status_code": 400, "message": f"Invalid Stripe webhook: {exc}"}

    event_dict = event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else dict(event)
    event_id = str(event_dict.get("id") or "")
    event_type = str(event_dict.get("type") or "")
    if event_type not in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        first_delivery = record_event_once(
            provider="stripe", event_id=event_id, event_type=event_type,
            raw_body=raw_body, database_url=database_url,
        )
        return {
            "ok": True, "status_code": 200, "event": event_type,
            "activated": False, "duplicate": not first_delivery,
        }

    session = ((event_dict.get("data") or {}).get("object") or {})
    session_id = str(session.get("id") or "")
    # Activation is idempotent. Persist the event only after verification so
    # failed deliveries remain retryable.
    result = verify_and_activate_stripe_session(session_id, database_url=database_url)
    if result.get("ok"):
        first_delivery = record_event_once(
            provider="stripe", event_id=event_id, event_type=event_type,
            raw_body=raw_body, database_url=database_url,
        )
        result["duplicate"] = not first_delivery
    return {**result, "status_code": 200 if result.get("ok") else 400, "event": event_type}
