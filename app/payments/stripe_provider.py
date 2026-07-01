"""Stripe Checkout integration for ProjectReady AI.

The active Stripe environment is selected with PROJECTREADY_STRIPE_MODE. Test
and live credentials are kept in separate environment variables so the user can
switch safely without overwriting production secrets.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from app.payments.store import (
    activate_purchase,
    get_purchase,
    get_purchase_by_reference,
    get_purchase_by_session,
    record_event_once,
    set_checkout_session,
)

# Legacy variables remain supported as fallbacks. New deployments should use
# the mode-specific variables documented in PAYMENT_SETUP.md.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
CANCEL_PATH = os.environ.get("PROJECTREADY_PAYMENT_CANCEL_PATH", "/workspace").strip() or "/workspace"


class StripePaymentError(RuntimeError):
    pass


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def stripe_mode() -> str:
    value = os.environ.get("PROJECTREADY_STRIPE_MODE", "live").strip().lower()
    if value in {"test", "sandbox"}:
        return "test"
    if value in {"live", "production", "prod"}:
        return "live"
    raise StripePaymentError("PROJECTREADY_STRIPE_MODE must be either 'test' or 'live'.")


def stripe_test_mode() -> bool:
    return stripe_mode() == "test"


def force_stripe_for_testing() -> bool:
    return stripe_test_mode() and (
        _env_true("PROJECTREADY_FORCE_STRIPE")
        or _env_true("PROJECTREADY_FORCE_STRIPE_TESTING")
    )


def configured_stripe_secret_key() -> str:
    mode = stripe_mode()
    if mode == "test":
        key = os.environ.get("STRIPE_TEST_SECRET_KEY", "").strip() or STRIPE_SECRET_KEY
        expected_prefixes = ("sk_test_", "rk_test_")
        variable_name = "STRIPE_TEST_SECRET_KEY"
    else:
        key = os.environ.get("STRIPE_LIVE_SECRET_KEY", "").strip() or STRIPE_SECRET_KEY
        expected_prefixes = ("sk_live_", "rk_live_")
        variable_name = "STRIPE_LIVE_SECRET_KEY"

    if not key:
        raise StripePaymentError(f"{variable_name} is not configured for Stripe {mode} mode.")
    if not key.startswith(expected_prefixes):
        raise StripePaymentError(
            f"The configured Stripe key does not match {mode} mode. "
            f"Use a {'test' if mode == 'test' else 'live'} secret key."
        )
    return key


def configured_stripe_webhook_secret() -> str:
    mode = stripe_mode()
    if mode == "test":
        secret = os.environ.get("STRIPE_TEST_WEBHOOK_SECRET", "").strip() or STRIPE_WEBHOOK_SECRET
        variable_name = "STRIPE_TEST_WEBHOOK_SECRET"
    else:
        secret = os.environ.get("STRIPE_LIVE_WEBHOOK_SECRET", "").strip() or STRIPE_WEBHOOK_SECRET
        variable_name = "STRIPE_LIVE_WEBHOOK_SECRET"
    if not secret:
        raise StripePaymentError(f"{variable_name} is not configured for Stripe {mode} mode.")
    if not secret.startswith("whsec_"):
        raise StripePaymentError(f"{variable_name} must be a Stripe webhook signing secret beginning with whsec_.")
    return secret


def stripe_environment_payload() -> Dict[str, Any]:
    mode = stripe_mode()
    try:
        secret_configured = bool(configured_stripe_secret_key())
    except StripePaymentError:
        secret_configured = False
    try:
        webhook_configured = bool(configured_stripe_webhook_secret())
    except StripePaymentError:
        webhook_configured = False
    return {
        "mode": mode,
        "test_mode": mode == "test",
        "force_stripe": force_stripe_for_testing(),
        "test_checkout_key_required": bool(
            mode == "test" and os.environ.get("PROJECTREADY_STRIPE_TEST_CHECKOUT_KEY", "").strip()
        ),
        "secret_key_configured": secret_configured,
        "webhook_secret_configured": webhook_configured,
    }


def _stripe_module():
    key = configured_stripe_secret_key()
    try:
        import stripe
    except ImportError as exc:
        raise StripePaymentError("Install the Stripe SDK with: pip install stripe") from exc
    stripe.api_key = key
    return stripe


def amount_to_subunit(amount: float) -> int:
    return int(round(float(amount) * 100))


def initialize_stripe_payment(purchase: Dict[str, Any], *, database_url: str = "") -> Dict[str, Any]:
    stripe = _stripe_module()
    environment = stripe_mode()
    purchase_metadata = purchase.get("metadata_json") or {}
    if not isinstance(purchase_metadata, dict):
        purchase_metadata = {}
    purchase_mode = str(purchase_metadata.get("purchase_mode") or "chapter")
    return_path = str(purchase_metadata.get("return_path") or CANCEL_PATH)
    if not return_path.startswith("/") or return_path.startswith("//"):
        return_path = CANCEL_PATH
    if purchase_mode == "topic_ideas":
        description = (
            "Unlock one full generation of up to 12 topic ideas after the two-idea free preview, with proposed "
            "objectives, trend-grounded literature metadata, possible data sources and instrument-source suggestions."
        )
    elif purchase_mode == "revision_only":
        description = "One guided chapter-strengthening working revision, one compliance review, and one editable DOCX export."
    else:
        description = "One guided chapter working draft, one strengthening revision, one compliance review, and one editable DOCX export."
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
        "payment_environment": environment,
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
        "payment_environment": environment,
        "test_mode": environment == "test",
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


def _stripe_object_to_dict(value: Any) -> Dict[str, Any]:
    """Convert StripeObject, dict-like, or mapping values into a plain dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        try:
            converted = value.to_dict_recursive()
            if isinstance(converted, dict):
                return converted
        except Exception:
            pass
    if hasattr(value, "items"):
        try:
            return {str(key): item for key, item in value.items()}
        except Exception:
            return {}
    try:
        converted = dict(value)
        return converted if isinstance(converted, dict) else {}
    except Exception:
        return {}


def _session_to_dict(session: Any) -> Dict[str, Any]:
    return _stripe_object_to_dict(session)


def _purchase_for_stripe_session(data: Dict[str, Any], *, database_url: str = "") -> Dict[str, Any] | None:
    metadata = _stripe_object_to_dict(data.get("metadata"))
    provider_reference = str(metadata.get("provider_reference") or "").strip()
    purchase_id = str(metadata.get("purchase_id") or data.get("client_reference_id") or "").strip()
    session_id = str(data.get("id") or "").strip()

    purchase = None
    if provider_reference:
        purchase = get_purchase_by_reference(provider_reference, database_url=database_url)
    if purchase is None and purchase_id:
        purchase = get_purchase(purchase_id, database_url=database_url)
    if purchase is None and session_id:
        purchase = get_purchase_by_session(session_id, database_url=database_url)
    return purchase


def _payment_environment_for_purchase(purchase: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    purchase_metadata = purchase.get("metadata_json") or {}
    if not isinstance(purchase_metadata, dict):
        purchase_metadata = {}
    value = str(
        metadata.get("payment_environment")
        or purchase_metadata.get("payment_environment")
        or stripe_mode()
    ).strip().lower()
    return "test" if value in {"test", "sandbox"} else "live"


def verify_and_activate_stripe_session_data(
    session_data: Any,
    *,
    database_url: str = "",
) -> Dict[str, Any]:
    """Verify and activate using an authenticated Stripe Checkout Session payload."""
    data = _session_to_dict(session_data)
    if not data:
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe supplied an empty Checkout Session payload.",
        }

    metadata = _stripe_object_to_dict(data.get("metadata"))
    purchase = _purchase_for_stripe_session(data, database_url=database_url)
    if not purchase:
        return {
            "ok": False,
            "activated": False,
            "message": "No ProjectReady purchase matches this Stripe Checkout Session.",
        }

    reference = str(metadata.get("provider_reference") or purchase.get("provider_reference") or "").strip()
    if not reference:
        return {
            "ok": False,
            "activated": False,
            "message": "The Stripe Checkout Session has no ProjectReady payment reference.",
        }

    metadata_purchase_id = str(metadata.get("purchase_id") or data.get("client_reference_id") or "").strip()
    if metadata_purchase_id and metadata_purchase_id != str(purchase.get("id") or ""):
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe purchase metadata does not match the stored ProjectReady purchase.",
        }

    metadata_project_id = str(metadata.get("project_id") or "").strip()
    if metadata_project_id and metadata_project_id != str(purchase.get("project_id") or ""):
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe project metadata does not match the stored ProjectReady project.",
        }

    expected_environment = _payment_environment_for_purchase(purchase, metadata)
    if "livemode" in data:
        received_environment = "live" if bool(data.get("livemode")) else "test"
        if received_environment != expected_environment:
            return {
                "ok": False,
                "activated": False,
                "message": "Stripe test/live environment does not match the stored ProjectReady purchase.",
                "received_environment": received_environment,
                "expected_environment": expected_environment,
            }
    else:
        received_environment = expected_environment

    payment_status = str(data.get("payment_status") or "").lower()
    if payment_status != "paid":
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe has not marked this checkout as paid.",
            "payment_status": data.get("payment_status"),
        }

    try:
        amount_total = int(data.get("amount_total") or 0)
        expected_subunit = amount_to_subunit(float(purchase["amount"]))
    except (TypeError, ValueError, KeyError) as exc:
        raise StripePaymentError(
            f"Could not validate the Stripe payment amount: {type(exc).__name__}: {exc}"
        ) from exc

    currency = str(data.get("currency") or "").upper()
    expected_currency = str(purchase.get("currency") or "").upper()
    if amount_total != expected_subunit or currency != expected_currency:
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe amount or currency does not match the ProjectReady purchase.",
            "received_amount": amount_total,
            "expected_amount": expected_subunit,
            "received_currency": currency,
            "expected_currency": expected_currency,
        }

    customer_details = _stripe_object_to_dict(data.get("customer_details"))
    stripe_email = str(customer_details.get("email") or data.get("customer_email") or "").strip().lower()
    purchase_email = str(purchase.get("user_email") or "").strip().lower()
    if stripe_email and purchase_email and stripe_email != purchase_email:
        return {
            "ok": False,
            "activated": False,
            "message": "Stripe customer email does not match the ProjectReady purchase.",
        }

    activated = activate_purchase(
        provider_reference=reference,
        verified_amount=amount_total / 100,
        verified_currency=currency,
        provider_payload=data,
        database_url=database_url,
    )
    return {
        "ok": True,
        "activated": True,
        "payment_environment": received_environment,
        "test_mode": received_environment == "test",
        "purchase": activated,
        "session": data,
    }


def verify_and_activate_stripe_session(session_id: str, *, database_url: str = "") -> Dict[str, Any]:
    stripe = _stripe_module()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise StripePaymentError(
            f"Stripe session verification failed: {type(exc).__name__}: {exc}"
        ) from exc
    return verify_and_activate_stripe_session_data(session, database_url=database_url)


def handle_stripe_webhook(
    *,
    raw_body: bytes,
    signature: str,
    database_url: str = "",
) -> Dict[str, Any]:
    webhook_secret = configured_stripe_webhook_secret()
    stripe = _stripe_module()
    try:
        event = stripe.Webhook.construct_event(raw_body, signature, webhook_secret)
    except Exception as exc:
        return {"ok": False, "status_code": 400, "message": f"Invalid Stripe webhook: {exc}"}

    event_dict = _stripe_object_to_dict(event)
    if not event_dict:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Stripe webhook event could not be converted into a readable payload.",
        }
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
            "payment_environment": stripe_mode(),
        }

    event_data = _stripe_object_to_dict(event_dict.get("data"))
    session = _stripe_object_to_dict(event_data.get("object"))
    result = verify_and_activate_stripe_session_data(session, database_url=database_url)
    if result.get("ok"):
        first_delivery = record_event_once(
            provider="stripe", event_id=event_id, event_type=event_type,
            raw_body=raw_body, database_url=database_url,
        )
        result["duplicate"] = not first_delivery
    return {**result, "status_code": 200 if result.get("ok") else 400, "event": event_type}
