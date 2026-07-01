"""Route ProjectReady AI checkout by billing country.

African billing countries normally use Paystack and all other countries use
Stripe. During an explicitly enabled Stripe test run, every checkout can be
forced through Stripe so all paid modules can be verified from Ghana without
moving real money.
"""
from __future__ import annotations

import os

AFRICAN_COUNTRY_CODES = {
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CV", "CM", "CF", "TD",
    "KM", "CG", "CD", "CI", "DJ", "EG", "GQ", "ER", "SZ", "ET",
    "GA", "GM", "GH", "GN", "GW", "KE", "LS", "LR", "LY", "MG",
    "MW", "ML", "MR", "MU", "MA", "MZ", "NA", "NE", "NG", "RW",
    "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "TZ", "TG",
    "TN", "UG", "ZM", "ZW",
}


def _env_true(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def stripe_payment_mode() -> str:
    value = str(os.environ.get("PROJECTREADY_STRIPE_MODE", "live")).strip().lower()
    return "test" if value in {"test", "sandbox"} else "live"


def force_stripe_for_testing() -> bool:
    return stripe_payment_mode() == "test" and (
        _env_true("PROJECTREADY_FORCE_STRIPE")
        or _env_true("PROJECTREADY_FORCE_STRIPE_TESTING")
    )


def normalise_country_code(country_code: str) -> str:
    code = str(country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("billing_country must be a two-letter ISO country code, for example GH or GB.")
    return code


def is_african_country(country_code: str) -> bool:
    return normalise_country_code(country_code) in AFRICAN_COUNTRY_CODES


def choose_payment_provider(country_code: str) -> str:
    normalise_country_code(country_code)
    if force_stripe_for_testing():
        return "stripe"
    return "paystack" if is_african_country(country_code) else "stripe"
