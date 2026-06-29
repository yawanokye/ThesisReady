"""Paystack checkout for ProjectReady AI.

The public plan price remains the approved USD amount. Paystack is used for
African billing countries and receives a GHS charge. You can set fixed GHS
prices per plan in Render, or use one configured USD-to-GHS rate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from app.payments.entitlements import get_price
from app.payments.store import activate_purchase, get_purchase_by_reference, record_event_once

PAYSTACK_BASE_URL = "https://api.paystack.co"
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
CANCEL_PATH = os.environ.get("PROJECTREADY_PAYMENT_CANCEL_PATH", "/workspace").strip() or "/workspace"
PAYSTACK_USER_AGENT = os.environ.get(
    "PAYSTACK_USER_AGENT",
    "ProjectReadyAI/1.0 (+https://projectreadyai.com; payments@projectreadyai.com)",
).strip()

PLAN_GHS_ENV = {
    "bachelors_chapter": "PROJECTREADY_PAYSTACK_BACHELORS_GHS",
    "masters_chapter": "PROJECTREADY_PAYSTACK_MASTERS_GHS",
    "doctorate_chapter": "PROJECTREADY_PAYSTACK_DOCTORATE_GHS",
    "bachelors_revision": "PROJECTREADY_PAYSTACK_BACHELORS_REVISION_GHS",
    "masters_revision": "PROJECTREADY_PAYSTACK_MASTERS_REVISION_GHS",
    "doctorate_revision": "PROJECTREADY_PAYSTACK_DOCTORATE_REVISION_GHS",
    "topic_ideas_access": "PROJECTREADY_PAYSTACK_TOPIC_IDEAS_GHS",
}

PLAN_GHS_DEFAULTS = {
    "topic_ideas_access": 10.00,
}


class PaystackError(RuntimeError):
    pass


def _require_secret_key() -> str:
    if not PAYSTACK_SECRET_KEY:
        raise PaystackError("PAYSTACK_SECRET_KEY is not configured.")
    return PAYSTACK_SECRET_KEY


def _positive_float(raw: Any, *, name: str) -> float:
    try:
        value = float(str(raw).strip())
    except Exception as exc:
        raise PaystackError(f"{name} must be a valid positive number.") from exc
    if value <= 0:
        raise PaystackError(f"{name} must be greater than zero.")
    return value


def amount_to_subunit(amount: float) -> int:
    return int(round(float(amount) * 100))


def get_paystack_charge(plan_key: str) -> Dict[str, Any]:
    """Return the exact GHS amount sent to Paystack.

    Preferred production setup: configure a fixed GHS price for each plan.
    Fallback setup: convert the fixed USD plan price using the configured rate.
    """
    price = get_price(plan_key)
    fixed_env_name = PLAN_GHS_ENV.get(str(plan_key).strip().lower())
    fixed_raw = os.environ.get(fixed_env_name, "").strip() if fixed_env_name else ""

    plan_key_value = str(plan_key).strip().lower()
    if fixed_raw:
        charged_amount = round(_positive_float(fixed_raw, name=fixed_env_name or "fixed GHS price"), 2)
        calculation = "fixed_ghs_plan_price"
        exchange_rate: Optional[float] = None
    elif plan_key_value in PLAN_GHS_DEFAULTS:
        charged_amount = round(float(PLAN_GHS_DEFAULTS[plan_key_value]), 2)
        calculation = "default_fixed_ghs_plan_price"
        exchange_rate = None
    else:
        rate = _positive_float(
            os.environ.get("PROJECTREADY_PAYSTACK_USD_TO_GHS_RATE", "15.00"),
            name="PROJECTREADY_PAYSTACK_USD_TO_GHS_RATE",
        )
        charged_amount = round(float(price["amount"]) * rate, 2)
        calculation = "usd_price_converted_with_configured_rate"
        exchange_rate = rate

    return {
        "selected_amount": float(price["amount"]),
        "selected_currency": "USD",
        "selected_display": price["display"],
        "amount": charged_amount,
        "currency": "GHS",
        "amount_subunit": amount_to_subunit(charged_amount),
        "charged_display": f"GHS {charged_amount:,.2f}",
        "calculation": calculation,
        "exchange_rate": exchange_rate,
    }


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    secret = _require_secret_key()
    url = f"{PAYSTACK_BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method.upper(),
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": PAYSTACK_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PaystackError(f"Paystack HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise PaystackError(f"Paystack request failed: {exc}") from exc


def initialize_paystack_payment(
    purchase: Dict[str, Any],
    *,
    callback_path: str = "/payment/paystack/callback",
) -> Dict[str, Any]:
    metadata = {
        "product": "ProjectReady AI",
        "purchase_id": purchase["id"],
        "project_id": purchase["project_id"],
        "chapter_key": purchase["chapter_key"],
        "chapter_number": purchase["chapter_number"],
        "academic_level": purchase["academic_level"],
        "plan_key": purchase["plan_key"],
        "display_amount": float(purchase.get("display_amount") or 0),
        "display_currency": purchase.get("display_currency") or "USD",
        "charged_amount": float(purchase["amount"]),
        "charged_currency": purchase["currency"],
        "cancel_action": f"{APP_BASE_URL}{CANCEL_PATH}?payment=cancelled&purchase_id={purchase['id']}",
    }
    payload = {
        "email": purchase["user_email"],
        "amount": str(amount_to_subunit(float(purchase["amount"]))),
        "currency": purchase["currency"],
        "reference": purchase["provider_reference"],
        "callback_url": f"{APP_BASE_URL}{callback_path}",
        "metadata": metadata,
    }
    response = _request("POST", "/transaction/initialize", payload)
    if not response.get("status"):
        raise PaystackError(response.get("message") or "Paystack initialization failed.")
    data = response.get("data") or {}
    return {
        "ok": True,
        "provider": "paystack",
        "checkout_url": data.get("authorization_url"),
        "authorization_url": data.get("authorization_url"),
        "access_code": data.get("access_code"),
        "provider_reference": data.get("reference") or purchase["provider_reference"],
        "purchase_id": purchase["id"],
        "amount": float(purchase["amount"]),
        "currency": purchase["currency"],
        "display_amount": float(purchase.get("display_amount") or 0),
        "display_currency": purchase.get("display_currency") or "USD",
        "access_token": purchase.get("access_token"),
    }


def verify_paystack_transaction(reference: str) -> Dict[str, Any]:
    safe_reference = urllib.parse.quote(str(reference or "").strip(), safe="")
    if not safe_reference:
        raise PaystackError("Payment reference is required.")
    response = _request("GET", f"/transaction/verify/{safe_reference}")
    if not response.get("status"):
        return {
            "ok": False,
            "verified": False,
            "message": response.get("message") or "Paystack verification failed.",
        }
    data = response.get("data") or {}
    return {
        "ok": True,
        "verified": str(data.get("status") or "").lower() == "success",
        "status": str(data.get("status") or "").lower(),
        "reference": data.get("reference"),
        "amount_subunit": int(data.get("amount") or 0),
        "amount": round(int(data.get("amount") or 0) / 100, 2),
        "currency": str(data.get("currency") or "").upper(),
        "customer_email": ((data.get("customer") or {}).get("email") or "").lower(),
        "data": data,
    }


def verify_and_activate_purchase(reference: str, *, database_url: str = "") -> Dict[str, Any]:
    verification = verify_paystack_transaction(reference)
    if not verification.get("verified"):
        return {
            "ok": False,
            "activated": False,
            "message": "The Paystack transaction is not successful.",
            "verification": verification,
        }

    purchase = get_purchase_by_reference(reference, database_url=database_url)
    if not purchase:
        return {
            "ok": False,
            "activated": False,
            "message": "Payment was verified, but its ProjectReady purchase was not found.",
        }

    expected_subunit = amount_to_subunit(float(purchase["amount"]))
    if verification["amount_subunit"] != expected_subunit:
        return {
            "ok": False,
            "activated": False,
            "message": "The verified Paystack amount does not match the chapter price.",
            "verification": verification,
        }
    if verification["currency"] != str(purchase["currency"]).upper():
        return {
            "ok": False,
            "activated": False,
            "message": "The verified Paystack currency does not match the chapter purchase.",
            "verification": verification,
        }
    if verification["customer_email"] and verification["customer_email"] != str(purchase["user_email"]).lower():
        return {
            "ok": False,
            "activated": False,
            "message": "The Paystack customer email does not match the chapter purchase.",
        }

    activated = activate_purchase(
        provider_reference=reference,
        verified_amount=verification["amount"],
        verified_currency=verification["currency"],
        provider_payload=verification["data"],
        database_url=database_url,
    )
    return {"ok": True, "activated": True, "purchase": activated, "verification": verification}


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = _require_secret_key().encode("utf-8")
    expected = hmac.new(secret, raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, str(signature or ""))


def handle_paystack_webhook(
    *,
    raw_body: bytes,
    signature: str,
    database_url: str = "",
) -> Dict[str, Any]:
    if not verify_webhook_signature(raw_body, signature):
        return {"ok": False, "status_code": 401, "message": "Invalid Paystack webhook signature."}

    event = json.loads(raw_body.decode("utf-8"))
    event_type = str(event.get("event") or "")
    data = event.get("data") or {}
    reference = str(data.get("reference") or "")
    event_id = str(data.get("id") or reference or hashlib.sha256(raw_body).hexdigest())

    if event_type != "charge.success" or not reference:
        first_delivery = record_event_once(
            provider="paystack", event_id=event_id, event_type=event_type,
            raw_body=raw_body, database_url=database_url,
        )
        return {
            "ok": True, "status_code": 200, "event": event_type,
            "activated": False, "duplicate": not first_delivery,
        }

    # Activation is idempotent. Record the webhook only after successful
    # verification so a transient provider/network error can be retried.
    result = verify_and_activate_purchase(reference, database_url=database_url)
    if result.get("ok"):
        first_delivery = record_event_once(
            provider="paystack", event_id=event_id, event_type=event_type,
            raw_body=raw_body, database_url=database_url,
        )
        result["duplicate"] = not first_delivery
    return {**result, "status_code": 200 if result.get("ok") else 400, "event": event_type}
