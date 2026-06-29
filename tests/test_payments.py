from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.payments import store as payment_store
from app.payments.entitlements import (
    build_plans_payload,
    is_free_generation_allowed,
    plan_key_for_level,
)
from app.payments.router import choose_payment_provider


class PaymentRulesTests(unittest.TestCase):
    def test_level_mapping(self):
        self.assertEqual(plan_key_for_level("Bachelors"), "bachelors_chapter")
        self.assertEqual(plan_key_for_level("Research Masters (e.g. MPhil)"), "masters_chapter")
        self.assertEqual(plan_key_for_level("PhD"), "doctorate_chapter")

    def test_country_routing(self):
        self.assertEqual(choose_payment_provider("GH"), "paystack")
        self.assertEqual(choose_payment_provider("NG"), "paystack")
        self.assertEqual(choose_payment_provider("GB"), "stripe")
        self.assertEqual(choose_payment_provider("US"), "stripe")

    def test_free_limit(self):
        allowed = is_free_generation_allowed(
            chapter_number=1,
            selected_section_ids=["a", "b", "c", "d", "e"],
        )
        self.assertTrue(allowed["allowed"])
        denied = is_free_generation_allowed(
            chapter_number=1,
            selected_section_ids=["a", "b", "c", "d", "e", "f"],
        )
        self.assertFalse(denied["allowed"])
        self.assertFalse(
            is_free_generation_allowed(chapter_number=2, selected_section_ids=["a"])["allowed"]
        )
        self.assertFalse(
            is_free_generation_allowed(
                chapter_number=1,
                selected_section_ids=["a"],
                revision_mode=True,
            )["allowed"]
        )

    def test_plan_payload_contains_revision(self):
        payload = build_plans_payload("Bachelors")
        plan = next(p for p in payload["paid_plans"] if p["recommended"])
        self.assertEqual(plan["includes"]["initial_draft"], 1)
        self.assertEqual(plan["includes"]["revision"], 1)
        self.assertEqual(plan["includes"]["compliance_check"], 1)
        self.assertEqual(plan["includes"]["docx_export"], 1)


class PaymentDatabasePathTests(unittest.TestCase):
    def setUp(self):
        self.original_payment_db = payment_store.SQLITE_PAYMENT_DB
        self.original_project_path = os.environ.pop("PROJECTREADY_SQLITE_DB_PATH", None)
        payment_store.SQLITE_PAYMENT_DB = ""

    def tearDown(self):
        payment_store.SQLITE_PAYMENT_DB = self.original_payment_db
        if self.original_project_path is not None:
            os.environ["PROJECTREADY_SQLITE_DB_PATH"] = self.original_project_path
        else:
            os.environ.pop("PROJECTREADY_SQLITE_DB_PATH", None)

    def test_plain_database_url_uses_persistent_disk_path(self):
        self.assertEqual(
            payment_store._sqlite_path("/var/data/projectready.db"),
            Path("/var/data/projectready.db"),
        )

    def test_sqlite_url_uses_persistent_disk_path(self):
        self.assertEqual(
            payment_store._sqlite_path("sqlite:////var/data/projectready.db"),
            Path("/var/data/projectready.db"),
        )

    def test_purchase_is_written_to_requested_sqlite_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "persistent" / "projectready.db"
            purchase = payment_store.create_pending_purchase(
                user_email="student@example.com",
                project_id="persistent-project",
                chapter_number=1,
                chapter_title="Introduction",
                academic_level="Bachelors",
                plan_key="bachelors_chapter",
                amount=4.99,
                currency="USD",
                display_amount=4.99,
                display_currency="USD",
                payment_provider="stripe",
                provider_reference="PRAI-ST-persistent-path-test",
                metadata={"test": True},
                database_url=str(target),
            )
            self.assertTrue(target.exists())
            restored = payment_store.get_purchase(
                purchase["id"],
                database_url=str(target),
            )
            self.assertIsNotNone(restored)
            self.assertEqual(restored["project_id"], "persistent-project")


class EntitlementStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        payment_store.SQLITE_PAYMENT_DB = os.path.join(self.tempdir.name, "payments.db")
        payment_store.DATABASE_URL = ""
        payment_store.init_payment_tables("")

    def tearDown(self):
        self.tempdir.cleanup()

    def _purchase(self):
        purchase = payment_store.create_pending_purchase(
            user_email="student@example.com",
            project_id="project-123",
            chapter_number=2,
            chapter_title="Literature Review",
            academic_level="Research Masters (e.g. MPhil)",
            plan_key="masters_chapter",
            amount=9.99,
            currency="USD",
            display_amount=9.99,
            display_currency="USD",
            payment_provider="stripe",
            provider_reference="PRAI-ST-test-reference",
            metadata={"test": True},
            database_url="",
        )
        return purchase

    def test_activation_checks_amount(self):
        purchase = self._purchase()
        with self.assertRaises(ValueError):
            payment_store.activate_purchase(
                provider_reference=purchase["provider_reference"],
                verified_amount=8.99,
                verified_currency="USD",
                database_url="",
            )

        activated = payment_store.activate_purchase(
            provider_reference=purchase["provider_reference"],
            verified_amount=9.99,
            verified_currency="USD",
            database_url="",
        )
        self.assertEqual(activated["status"], "paid")

    def test_claim_complete_and_no_second_use(self):
        purchase = self._purchase()
        payment_store.activate_purchase(
            provider_reference=purchase["provider_reference"],
            verified_amount=9.99,
            verified_currency="USD",
            database_url="",
        )
        claim = payment_store.claim_entitlement(
            purchase_id=purchase["id"],
            access_token=purchase["access_token"],
            project_id="project-123",
            chapter_number=2,
            chapter_title="Literature Review",
            action="draft",
            idempotency_key="draft-request-1",
            database_url="",
        )
        self.assertTrue(claim["claimed"])
        payment_store.complete_claim(claim["usage"]["id"], database_url="")

        with self.assertRaises(PermissionError):
            payment_store.claim_entitlement(
                purchase_id=purchase["id"],
                access_token=purchase["access_token"],
                project_id="project-123",
                chapter_number=2,
                chapter_title="Literature Review",
                action="draft",
                idempotency_key="draft-request-2",
                database_url="",
            )

    def test_rollback_returns_credit_and_same_request_can_retry(self):
        purchase = self._purchase()
        payment_store.activate_purchase(
            provider_reference=purchase["provider_reference"],
            verified_amount=9.99,
            verified_currency="USD",
            database_url="",
        )
        first = payment_store.claim_entitlement(
            purchase_id=purchase["id"],
            access_token=purchase["access_token"],
            project_id="project-123",
            chapter_number=2,
            chapter_title="Literature Review",
            action="revision",
            idempotency_key="revision-request-1",
            database_url="",
        )
        payment_store.rollback_claim(first["usage"]["id"], database_url="")

        retried = payment_store.claim_entitlement(
            purchase_id=purchase["id"],
            access_token=purchase["access_token"],
            project_id="project-123",
            chapter_number=2,
            chapter_title="Literature Review",
            action="revision",
            idempotency_key="revision-request-1",
            database_url="",
        )
        self.assertTrue(retried["claimed"])

    def test_wrong_project_is_rejected(self):
        purchase = self._purchase()
        payment_store.activate_purchase(
            provider_reference=purchase["provider_reference"],
            verified_amount=9.99,
            verified_currency="USD",
            database_url="",
        )
        with self.assertRaises(PermissionError):
            payment_store.claim_entitlement(
                purchase_id=purchase["id"],
                access_token=purchase["access_token"],
                project_id="different-project",
                chapter_number=2,
                chapter_title="Literature Review",
                action="export",
                idempotency_key="export-request-1",
                database_url="",
            )


if __name__ == "__main__":
    unittest.main()
