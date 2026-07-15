"""Report stale or unsafe ProjectReady AI production environment settings.

This script never prints secret values. Run it inside the Render web-service shell:
    python scripts/audit_environment.py
"""
from __future__ import annotations

import os

DEPRECATED = {
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_FAST_MODEL",
    "DEEPSEEK_REASONER_MODEL", "DEEPSEEK_TOPIC_IDEA_MAX_TOKENS",
    "DEEPSEEK_TOPIC_IDEA_MODEL", "DEEPSEEK_TOPIC_IDEA_REASONING_EFFORT",
    "DEEPSEEK_TOPIC_IDEA_THINKING", "DEEPSEEK_TOPIC_IDEA_TIMEOUT_SECONDS",
    "HUMANIZER_API_KEY", "HUMANIZER_ENABLED", "HUMANIZER_ENDPOINT",
    "HUMANIZER_FALLBACK_TO_INTERNAL", "HUMANIZER_MODEL",
    "HUMANIZER_REPLACE_INTERNAL", "HUMANIZER_TIMEOUT",
    "OPENAI_DRAFT_MODEL", "OPENAI_FINAL_MODEL", "OPENAI_TIMEOUT_SECONDS",
    "PROJECTREADY_ENABLE_DEEPSEEK", "PROJECTREADY_DEFAULT_MODE",
    "PROJECTREADY_EXTRA_AI_PASSES", "PROJECTREADY_PREMIUM_REVIEW",
    "PROJECTREADY_DRAFT_TEMPERATURE", "PROJECTREADY_REVISION_TEMPERATURE",
    "PROJECTREADY_SMALL_MODEL_STYLE", "PROJECTREADY_STYLE_TEXTURE",
    "PROJECTREADY_ALLOW_PARAGRAPH_REORDER", "PROJECTREADY_ALLOW_SURFACE_NOISE",
    "PROJECTREADY_AUTO_EXPAND_SHORT_DRAFT", "PROJECTREADY_FORCE_STRIPE",
    "PROJECTREADY_STRIPE_MODE", "PROJECTREADY_STRIPE_TEST_CHECKOUT_KEY",
    "STRIPE_TEST_SECRET_KEY", "STRIPE_TEST_WEBHOOK_SECRET",
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "PAYSTACK_PUBLIC_KEY",
    "PAYSTACK_CALLBACK_PATH", "PAYSTACK_WEBHOOK_PATH",
}

MODEL_VARS = {
    name for name in os.environ
    if name.startswith("OPENAI_") and name.endswith("MODEL")
}

problems: list[str] = []
for name in sorted(DEPRECATED):
    if os.getenv(name, "").strip():
        problems.append(f"Deprecated variable is still set: {name}")

for name in sorted(MODEL_VARS):
    model = os.getenv(name, "").strip()
    if model and not model.startswith("gpt-5.6-"):
        problems.append(f"Non-GPT-5.6 model configured in {name}: {model}")

required = ["DATABASE_URL", "OPENAI_API_KEY"]
for name in required:
    if not os.getenv(name, "").strip():
        problems.append(f"Required variable is missing: {name}")

plain_key = os.getenv("PROJECTREADY_INTERNAL_ACCESS_KEY", "").strip()
key_hash = os.getenv("PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256", "").strip()
secret = os.getenv("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET", "").strip()
if plain_key:
    problems.append("Plain internal access key is set. Use only PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256 in production.")
if key_hash and (len(key_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in key_hash)):
    problems.append("PROJECTREADY_INTERNAL_ACCESS_KEY_SHA256 is not a valid 64-character SHA-256 hex digest.")
if os.getenv("PROJECTREADY_INTERNAL_ACCESS_EMAILS", "").strip() and len(secret) < 32:
    problems.append("PROJECTREADY_INTERNAL_ACCESS_SIGNING_SECRET must contain at least 32 characters.")

if problems:
    print("ProjectReady environment audit found issues:")
    for item in problems:
        print(f"- {item}")
    raise SystemExit(1)

print("ProjectReady environment audit passed.")
