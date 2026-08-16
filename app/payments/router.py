"""Route ProjectReady AI checkout by billing country.

African billing countries use Paystack. Other billing countries use Stripe.
This module is production/live-payment focused and does not issue internal
trial-payment entitlements.
"""
from __future__ import annotations

AFRICAN_COUNTRY_CODES = {
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CV", "CM", "CF", "TD",
    "KM", "CG", "CD", "CI", "DJ", "EG", "GQ", "ER", "SZ", "ET",
    "GA", "GM", "GH", "GN", "GW", "KE", "LS", "LR", "LY", "MG",
    "MW", "ML", "MR", "MU", "MA", "MZ", "NA", "NE", "NG", "RW",
    "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "TZ", "TG",
    "TN", "UG", "ZM", "ZW",
}


def normalise_country_code(country_code: str) -> str:
    code = str(country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("billing_country must be a two-letter ISO country code, for example GH or GB.")
    return code


def is_african_country(country_code: str) -> bool:
    return normalise_country_code(country_code) in AFRICAN_COUNTRY_CODES


def choose_payment_provider(country_code: str) -> str:
    """Choose the customer-facing payment provider safely.

    African billing countries normally use Paystack. A Stripe test deployment may
    force Stripe only when the additional test-routing safety switch is enabled.
    This prevents a stale PROJECTREADY_STRIPE_MODE=test / PROJECTREADY_FORCE_STRIPE=1
    pair from blocking real African customers with a private Stripe test-key prompt.
    """
    import os

    mode = str(os.environ.get("PROJECTREADY_STRIPE_MODE", "live") or "live").strip().lower()
    force_stripe = str(os.environ.get("PROJECTREADY_FORCE_STRIPE", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    allow_test_routing = str(os.environ.get("PROJECTREADY_ENABLE_TEST_CHECKOUTS", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    if mode == "test" and force_stripe and allow_test_routing:
        return "stripe"
    return "paystack" if is_african_country(country_code) else "stripe"
