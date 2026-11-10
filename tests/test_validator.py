import os
import sqlite3
import unittest

from core.db import init_db, get_members, reset_demo_ledger
from core.ledger import (
    add_ledger_entry,
    calculate_derived_balances,
    reset_ledger,
    validate_transaction_logic,
    delete_latest_ledger_entry
)

TEST_DB = "test_validator.db"

class TestLogicalValidatorAndSequence(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        init_db(TEST_DB)
        self.members = get_members(TEST_DB)
        self.leela_id = next(m["id"] for m in self.members if m["name"] == "Leela")
        self.radha_id = next(m["id"] for m in self.members if m["name"] == "Radha")
        self.chitra_id = next(m["id"] for m in self.members if m["name"] == "Chitra")
        self.meeting_id = 1

        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
            (self.meeting_id, "audio/clips/v_test.mp3", "clip_hash_v")
        )
        self.clip_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def test_rule_d_positive_amount(self):
        ok, err = validate_transaction_logic(
            self.meeting_id, "Leela", "thrift", 0.0, "Radha", "president", db_path=TEST_DB
        )
        self.assertFalse(ok)
        self.assertIn("പൂജ്യത്തേക്കാൾ", err)

        ok, err = validate_transaction_logic(
            self.meeting_id, "Leela", "thrift", -50.0, "Radha", "president", db_path=TEST_DB
        )
        self.assertFalse(ok)

    def test_rule_b_no_self_confirmation(self):
        ok, err = validate_transaction_logic(
            self.meeting_id, "Leela", "thrift", 100.0, "Leela", "secretary", db_path=TEST_DB
        )
        self.assertFalse(ok)
        self.assertIn("സ്വയം സാക്ഷ്യപ്പെടുത്താൻ കഴിയില്ല", err)

    def test_rule_c_two_person_loan_governance(self):
        # Loan disbursement cannot be confirmed by secretary alone
        ok, err = validate_transaction_logic(
            self.meeting_id, "Radha", "loan_disbursement", 1000.0, "Leela", "secretary", db_path=TEST_DB
        )
        self.assertFalse(ok)
        self.assertIn("സെക്രട്ടറി മാത്രം നൽകാൻ പാടില്ല", err)

        # Loan disbursement CAN be confirmed by president — but first Meera must have thrift (Rule E)
        meera_id = next(m["id"] for m in self.members if m["name"] == "Meera")
        add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=meera_id,
            clip_id=self.clip_id,
            event_type="thrift",
            amount=300.0,
            confirmed_by=self.leela_id,
            db_path=TEST_DB
        )
        ok, err = validate_transaction_logic(
            self.meeting_id, "Meera", "loan_disbursement", 1000.0, "Radha", "president", db_path=TEST_DB
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_rule_e_thrift_eligibility_loan_block(self):
        """Rule E: loan_disbursement must be blocked when member has zero thrift savings."""
        # Case 1: Meera has ZERO thrift savings — loan must be BLOCKED
        ok, err = validate_transaction_logic(
            self.meeting_id, "Meera", "loan_disbursement", 500.0, "Radha", "president", db_path=TEST_DB
        )
        self.assertFalse(ok, "Expected loan to be blocked for member with zero thrift savings")
        self.assertIn("വായ്പാ യോഗ്യതാ നിയമം", err)
        self.assertIn("Loan Eligibility Rule", err)

        # Case 2: First deposit thrift for Meera, then loan should be ALLOWED
        meera_id = next(m["id"] for m in self.members if m["name"] == "Meera")
        add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=meera_id,
            clip_id=self.clip_id,
            event_type="thrift",
            amount=200.0,
            confirmed_by=self.leela_id,
            db_path=TEST_DB
        )
        ok2, err2 = validate_transaction_logic(
            self.meeting_id, "Meera", "loan_disbursement", 500.0, "Radha", "president", db_path=TEST_DB
        )
        self.assertTrue(ok2, f"Expected loan to be allowed after thrift deposit, but got: {err2}")
        self.assertIsNone(err2)

    def test_rule_a_loan_repayment_validation(self):
        # Case 1: Member has zero outstanding loan -> repayment must be blocked
        ok, err = validate_transaction_logic(
            self.meeting_id, "Chitra", "repayment", 500.0, "Leela", "secretary", db_path=TEST_DB
        )
        self.assertFalse(ok)
        self.assertIn("തിരിച്ചടയ്ക്കാൻ വായ്പാ ബാക്കിയില്ല", err)

        # Disburse ₹1000 loan to Chitra — first add thrift so Rule E is satisfied
        add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.chitra_id,
            clip_id=self.clip_id,
            event_type="thrift",
            amount=500.0,
            confirmed_by=self.radha_id,
            db_path=TEST_DB
        )
        add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.chitra_id,
            clip_id=self.clip_id,
            event_type="loan_disbursement",
            amount=1000.0,
            confirmed_by=self.radha_id,
            db_path=TEST_DB
        )

        # Case 2: Repayment greater than outstanding debt (₹1200 > ₹1000) -> must be blocked
        ok, err = validate_transaction_logic(
            self.meeting_id, "Chitra", "repayment", 1200.0, "Leela", "secretary", db_path=TEST_DB
        )
        self.assertFalse(ok)
        self.assertIn("അധിക തിരിച്ചടവ്", err)

        # Case 3: Valid repayment (₹500 <= ₹1000) -> must pass
        ok, err = validate_transaction_logic(
            self.meeting_id, "Chitra", "repayment", 500.0, "Leela", "secretary", db_path=TEST_DB
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_sequence_reset_and_start_at_id_one(self):
        # Add an entry -> gets an ID
        e1 = add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.leela_id,
            clip_id=self.clip_id,
            event_type="thrift",
            amount=100.0,
            confirmed_by=self.radha_id,
            db_path=TEST_DB
        )
        self.assertEqual(e1, 1)

        # Add second entry -> ID 2
        e2 = add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.radha_id,
            clip_id=self.clip_id,
            event_type="thrift",
            amount=200.0,
            confirmed_by=self.leela_id,
            db_path=TEST_DB
        )
        self.assertEqual(e2, 2)

        # Reset ledger (reset_ledger or reset_demo_ledger)
        reset_ledger(self.meeting_id, db_path=TEST_DB)

        # Add clip and entry again
        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
            (self.meeting_id, "audio/clips/v_test2.mp3", "clip_hash_v2")
        )
        new_clip_id = cur.lastrowid
        conn.commit()
        conn.close()

        # The new entry MUST start cleanly at ID 1!
        new_e1 = add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.leela_id,
            clip_id=new_clip_id,
            event_type="thrift",
            amount=100.0,
            confirmed_by=self.radha_id,
            db_path=TEST_DB
        )
        self.assertEqual(new_e1, 1, f"Expected ID 1 after reset, but got {new_e1}")

if __name__ == "__main__":
    unittest.main()

