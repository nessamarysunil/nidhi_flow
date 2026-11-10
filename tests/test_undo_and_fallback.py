import os
import sqlite3
import unittest
from unittest.mock import patch

from core.db import init_db, get_members
from core.ledger import (
    add_ledger_entry,
    verify_chain,
    calculate_derived_balances,
    delete_latest_ledger_entry,
    reset_ledger
)
from core.gnani_client import process_voice_entry

TEST_DB = "test_undo_fallback.db"

class TestUndoAndFallback(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        init_db(TEST_DB)
        self.members = get_members(TEST_DB)
        self.leela_id = next(m["id"] for m in self.members if m["name"] == "Leela")
        self.radha_id = next(m["id"] for m in self.members if m["name"] == "Radha")
        self.meeting_id = 1

        # Add dummy audio clip
        conn = sqlite3.connect(TEST_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
            (self.meeting_id, "audio/clips/dummy.mp3", "dummy_clip_hash_123")
        )
        self.clip_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def test_undo_latest_ledger_entry_maintains_cryptographic_chain(self):
        # 1. Add Block 1: Leela thrift ₹100
        b1 = add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.leela_id,
            clip_id=self.clip_id,
            event_type="thrift",
            amount=100.0,
            confirmed_by=self.radha_id,
            db_path=TEST_DB
        )
        # 2. Add Block 2: Radha loan ₹1000
        b2 = add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.radha_id,
            clip_id=self.clip_id,
            event_type="loan_disbursement",
            amount=1000.0,
            confirmed_by=self.leela_id,
            db_path=TEST_DB
        )
        # 3. Add Block 3 (Duplicate): Radha loan ₹1000 again
        b3 = add_ledger_entry(
            meeting_id=self.meeting_id,
            member_id=self.radha_id,
            clip_id=self.clip_id,
            event_type="loan_disbursement",
            amount=1000.0,
            confirmed_by=self.leela_id,
            db_path=TEST_DB
        )

        bal_before = calculate_derived_balances(self.meeting_id, db_path=TEST_DB)
        self.assertEqual(bal_before["summary"]["total_disbursed"], 2000.0)

        # Undo duplicate Block 3
        res = delete_latest_ledger_entry(self.meeting_id, db_path=TEST_DB)
        self.assertTrue(res["success"])
        self.assertEqual(res["deleted_entry_id"], b3)
        self.assertEqual(res["amount"], 1000.0)

        # Chain must still be 100% valid
        v_res = verify_chain(self.meeting_id, db_path=TEST_DB)
        self.assertTrue(v_res["valid"], f"Chain was invalid after undo: {v_res}")

        # Balances must reflect removal
        bal_after = calculate_derived_balances(self.meeting_id, db_path=TEST_DB)
        self.assertEqual(bal_after["summary"]["total_disbursed"], 1000.0)
        self.assertEqual(bal_after["summary"]["total_savings"], 100.0)

    def test_empty_pass2_fallback_avoids_false_positive_discrepancy(self):
        # Mock Gnani STT: Pass 1 succeeds with "Leela 100 roopa", Pass 2 returns empty ""
        with patch("core.gnani_client.transcribe_clip") as mock_stt:
            def side_effect(audio_bytes, output_format="transcribe", keyterms=None):
                if output_format == "transcribe":
                    return {"success": True, "transcript": "Leela 100 roopa thrift"}
                else:
                    return {"success": True, "transcript": ""}

            mock_stt.side_effect = side_effect
            roster = ["Leela", "Radha", "Chitra"]
            res = process_voice_entry(b"fake_audio_bytes", roster)

            # Verification
            self.assertEqual(res["status"], "green")
            self.assertTrue(res["pass2_fallback_used"])
            self.assertEqual(res["amt1"], 100.0)
            self.assertEqual(res["amt2"], 100.0)
            self.assertEqual(res["matched_member"], "Leela")
            self.assertEqual(res["event_type"], "thrift")
            self.assertFalse(any("discrepancy" in r.lower() for r in res["reasons"]))

if __name__ == "__main__":
    unittest.main()
