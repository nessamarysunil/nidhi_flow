import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import init_db, get_members, get_db_connection
from core.ledger import (
    compute_entry_hash,
    get_latest_hash,
    add_ledger_entry,
    verify_chain,
    calculate_derived_balances,
    reset_ledger,
    validate_loan_confirmation,
    GENESIS_HASH
)
from core.fingerprint import (
    hash_to_fingerprint,
    hash_to_fingerprint_en,
    hash_to_fingerprint_spoken,
)
from core.gnani_client import (
    normalize_amount,
    match_member_from_text,
    detect_event_type,
    process_voice_entry
)

def run_tests():
    print("Running SabhaLedger Core Integration Tests...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        test_db = tf.name

    try:
        # 1. DB Init and Seed
        init_db(test_db)
        members = get_members(test_db)
        assert len(members) == 5, f"Expected 5 members, got {len(members)}"
        print("✓ DB Schema & Seeding passed")

        # 2. Check Genesis Hash
        latest = get_latest_hash(1, db_path=test_db)
        assert latest == GENESIS_HASH, f"Expected genesis hash, got {latest}"
        fp = hash_to_fingerprint(latest)
        assert fp == "Genesis Session — Awaiting Block #1", f"Expected genesis status, got '{fp}'"
        print(f"✓ Genesis status: '{fp}'")

        # 3. Audio clips insertion & Ledger Chaining
        conn = get_db_connection(test_db)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
            (1, "audio/clips/test1.wav", "abc123cliphash1")
        )
        clip1 = cur.lastrowid
        cur.execute(
            "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
            (1, "audio/clips/test2.wav", "def456cliphash2")
        )
        clip2 = cur.lastrowid
        cur.execute(
            "INSERT INTO audio_clips (meeting_id, file_path, clip_hash) VALUES (?, ?, ?);",
            (1, "audio/clips/test3.wav", "ghi789cliphash3")
        )
        clip3 = cur.lastrowid
        conn.commit()
        conn.close()

        sec_id = members[0]["id"] # Leela
        radha_id = members[1]["id"] # Radha
        chitra_id = members[2]["id"] # Chitra

        # Add Entry 1: Leela thrift ₹500
        e1 = add_ledger_entry(
            meeting_id=1, member_id=sec_id, clip_id=clip1,
            event_type="thrift", amount=500.0, confirmed_by=sec_id,
            db_path=test_db
        )

        # Add Entry 2: Radha loan disbursement ₹2000
        e2 = add_ledger_entry(
            meeting_id=1, member_id=radha_id, clip_id=clip2,
            event_type="loan_disbursement", amount=2000.0, confirmed_by=sec_id,
            db_path=test_db
        )

        # Add Entry 3: Radha repayment ₹500
        e3 = add_ledger_entry(
            meeting_id=1, member_id=radha_id, clip_id=clip3,
            event_type="repayment", amount=500.0, confirmed_by=sec_id,
            db_path=test_db
        )

        # 4. Verify Chain before tampering
        v_res = verify_chain(1, db_path=test_db)
        assert v_res["valid"] is True, f"Chain should be valid: {v_res}"
        print("✓ Sequential cryptographic hash chain verified intact")

        # 5. Check Derived Balances
        balances = calculate_derived_balances(1, db_path=test_db)
        summary = balances["summary"]
        assert summary["total_savings"] == 500.0
        assert summary["total_disbursed"] == 2000.0
        assert summary["total_repaid"] == 500.0
        assert summary["total_outstanding_debt"] == 1500.0
        assert balances["members"]["Radha"]["debt"] == 1500.0
        assert balances["members"]["Leela"]["savings"] == 500.0
        print("✓ Derived balances computed correctly:", summary)

        # 6. Meeting Fingerprint with entries
        h_latest = get_latest_hash(1, db_path=test_db)
        fp_active = hash_to_fingerprint(h_latest)
        fp_en = hash_to_fingerprint_en(h_latest)
        fp_spoken = hash_to_fingerprint_spoken(h_latest)
        assert len(fp_active.split(" • ")) == 6
        assert len(fp_en.split(" • ")) == 6
        assert len(fp_spoken.split(", ")) == 6
        print(f"✓ Active Meeting 6-Word Fingerprint (Malayalam): '{fp_active}'")
        print(f"✓ Active Meeting 6-Word Fingerprint (Transliteration): '{fp_en}'")
        print(f"✓ Active Meeting Spoken TTS String: '{fp_spoken}'")

        # 7. Tamper Engine: mutate entry 2 amount
        conn = get_db_connection(test_db)
        cur = conn.cursor()
        cur.execute("UPDATE ledger_entries SET amount = 9999.0 WHERE id = ?;", (e2,))
        conn.commit()
        conn.close()

        tamper_res = verify_chain(1, db_path=test_db)
        assert tamper_res["valid"] is False, "Tamper should have been caught!"
        assert tamper_res["broken_at_entry_id"] == e2
        print(f"✓ Tamper detection correctly caught mutation at block #{e2}: {tamper_res['reason']}")

        # 8. Test normalization and matching
        assert normalize_amount("Leela anooru roopa") == 500.0
        assert normalize_amount("Radha randaayiram roopa") == 2000.0
        assert normalize_amount("Meera aayiram") == 1000.0
        assert normalize_amount("Chitra nooru") == 100.0
        assert normalize_amount("Fine 50 rs") == 50.0

        names = [m["name"] for m in members]
        assert match_member_from_text("Leela thrift thannu", names)[0] == "Leela"
        assert match_member_from_text("Radha loan eduthu", names)[0] == "Radha"
        assert match_member_from_text("Meera adavu adachu", names)[0] == "Meera"

        # Test event type detection priority:
        # 1st: fine ('pizha adachu' -> fine)
        # 2nd: repayment ('vaaypa adachu' -> repayment)
        # 3rd: loan_disbursement ('loan vaaypa' -> loan_disbursement)
        # 4th: thrift ('thrift thannu' -> thrift)
        assert detect_event_type("Chitra 50 roopa pizha adachu") == "fine"
        assert detect_event_type("Radha 500 roopa vaaypa adachu") == "repayment"
        assert detect_event_type("Radha 2000 roopa vaypa eduthu") == "loan_disbursement"
        assert detect_event_type("Radha 1000 roopa loan vaaypa") == "loan_disbursement"
        assert detect_event_type("Meera 1000 roopa thirichadavu") == "repayment"
        assert detect_event_type("Leela 500 roopa thrift thannu") == "thrift"

        # 9. Test Two-Person Loan Confirmation Rule
        valid, err = validate_loan_confirmation("loan_disbursement", "secretary")
        assert valid is False, "Secretary alone should not confirm loan"
        assert "not the Secretary alone" in err
        valid, _ = validate_loan_confirmation("loan_disbursement", "president")
        assert valid is True
        valid, _ = validate_loan_confirmation("loan_disbursement", "member")
        assert valid is True
        valid, _ = validate_loan_confirmation("thrift", "secretary")
        assert valid is True
        print("✓ Two-person loan confirmation governance rule validated")

        # 10. Test Ledger Reset to Genesis
        reset_res = reset_ledger(1, db_path=test_db)
        assert reset_res["deleted_entries"] > 0
        assert get_latest_hash(1, db_path=test_db) == GENESIS_HASH
        assert hash_to_fingerprint(get_latest_hash(1, db_path=test_db)) == "Genesis Session — Awaiting Block #1"
        assert verify_chain(1, db_path=test_db)["valid"] is True
        print("✓ Reset demo ledger control validated (returns cleanly to Genesis)")

        print("All SabhaLedger automated tests PASSED successfully!")

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)

if __name__ == "__main__":
    run_tests()
