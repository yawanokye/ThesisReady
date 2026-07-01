from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.payments import store as payment_store
from app.payments.stripe_provider import (
    _stripe_object_to_dict,
    verify_and_activate_stripe_session_data,
)


class BrokenRecursiveMapping(dict):
    def to_dict_recursive(self):
        raise KeyError(0)


class StripeDataObject:
    """Mimics Stripe SDK objects that fail with dict(obj) / index 0."""

    def __init__(self, data):
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)

    def to_dict_recursive(self):
        raise KeyError(0)

    def __getitem__(self, key):
        raise KeyError(key)


class StripeWebhookActivationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        payment_store.SQLITE_PAYMENT_DB = os.path.join(self.tempdir.name, "payments.db")
        payment_store.DATABASE_URL = ""
        payment_store.init_payment_tables("")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_broken_recursive_stripe_object_falls_back_to_mapping(self):
        value = BrokenRecursiveMapping({"id": "evt_test", "type": "checkout.session.completed"})
        converted = _stripe_object_to_dict(value)
        self.assertEqual(converted["id"], "evt_test")

    def test_stripe_sdk_data_object_uses_internal_data_mapping(self):
        value = StripeDataObject(
            {
                "id": "cs_test_sdk",
                "payment_status": "paid",
                "metadata": StripeDataObject({"provider_reference": "PRAI-ST-sdk"}),
            }
        )
        converted = _stripe_object_to_dict(value)
        self.assertEqual(converted["id"], "cs_test_sdk")
        self.assertEqual(converted["metadata"]["provider_reference"], "PRAI-ST-sdk")

    def test_signed_session_payload_activates_without_second_api_request(self):
        purchase = payment_store.create_pending_purchase(
            user_email="student@example.com",
            project_id="project-123",
            chapter_number=1,
            chapter_title="Introduction",
            academic_level="Bachelors",
            plan_key="bachelors_chapter",
            amount=4.99,
            currency="USD",
            display_amount=4.99,
            display_currency="USD",
            payment_provider="stripe",
            provider_reference="PRAI-ST-webhook-test",
            metadata={"purchase_mode": "chapter", "return_path": "/workspace"},
            database_url="",
        )
        payment_store.set_checkout_session(purchase["id"], "cs_test_123", database_url="")

        session = BrokenRecursiveMapping(
            {
                "id": "cs_test_123",
                "client_reference_id": purchase["id"],
                "amount_total": 499,
                "currency": "usd",
                "payment_status": "paid",
                "customer_email": "student@example.com",
                "customer_details": BrokenRecursiveMapping({"email": "student@example.com"}),
                "metadata": BrokenRecursiveMapping(
                    {
                        "purchase_id": purchase["id"],
                        "provider_reference": "PRAI-ST-webhook-test",
                        "project_id": "project-123",
                        "chapter_number": "1",
                        "chapter_key": "chapter-1",
                        "purchase_mode": "chapter",
                    }
                ),
            }
        )

        result = verify_and_activate_stripe_session_data(session, database_url="")
        self.assertTrue(result["ok"])
        self.assertTrue(result["activated"])
        self.assertEqual(result["purchase"]["status"], "paid")


if __name__ == "__main__":
    unittest.main()
