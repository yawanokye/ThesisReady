"""Route ProjectReady AI checkout by the customer's selected billing country.

African billing countries use Paystack. All other billing countries use Stripe.
Never route by IP address because IP location can be inaccurate and does not
necessarily match the payer's billing country.
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
    return "paystack" if is_african_country(country_code) else "stripe"
