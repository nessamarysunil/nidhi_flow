import hashlib
import datetime
from .db import get_db_connection, get_members, DB_PATH

GENESIS_HASH = "0" * 64

def compute_entry_hash(prev_hash: str, meeting_id: int, member_id: int, clip_hash: str,
                       event_type: str, amount: float, confirmed_by: int, timestamp: str) -> str:
    """
    Construct canonical string:
    f"{prev_hash}|{meeting_id}|{member_id}|{clip_hash}|{event_type}|{amount:.2f}|{confirmed_by}|{timestamp}"
    and return its SHA-256 hex digest.
    """
    canonical = f"{prev_hash}|{meeting_id}|{member_id}|{clip_hash}|{event_type}|{amount:.2f}|{confirmed_by}|{timestamp}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def get_latest_hash(meeting_id: int, db_path: str = DB_PATH) -> str:
    """Fetch entry_hash of the latest row for that meeting, returning GENESIS_HASH if empty."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT entry_hash FROM ledger_entries WHERE meeting_id = ? ORDER BY id DESC LIMIT 1;",
        (meeting_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row and row["entry_hash"]:
        return row["entry_hash"]
    return GENESIS_HASH

def add_ledger_entry(meeting_id: int, member_id: int, clip_id: int, event_type: str,
                     amount: float, confirmed_by: int, clip_hash: str = None,
                     timestamp: str = None, db_path: str = DB_PATH) -> int:
    """
    Compute entry hash against the latest previous hash, then insert row into ledger_entries.
    Returns the new entry id.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now().isoformat()

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Look up clip_hash if not explicitly passed
    if clip_hash is None:
        cursor.execute("SELECT clip_hash FROM audio_clips WHERE id = ?;", (clip_id,))
        clip_row = cursor.fetchone()
        if not clip_row:
            conn.close()
            raise ValueError(f"audio_clip with id {clip_id} not found.")
        clip_hash = clip_row["clip_hash"]

    # Fetch latest hash as prev_hash
    cursor.execute(
        "SELECT entry_hash FROM ledger_entries WHERE meeting_id = ? ORDER BY id DESC LIMIT 1;",
        (meeting_id,)
    )
    last_row = cursor.fetchone()
    prev_hash = last_row["entry_hash"] if last_row and last_row["entry_hash"] else GENESIS_HASH

    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        meeting_id=meeting_id,
        member_id=member_id,
        clip_hash=clip_hash,
        event_type=event_type,
        amount=amount,
        confirmed_by=confirmed_by,
        timestamp=timestamp
    )

    cursor.execute("""
        INSERT INTO ledger_entries (
            meeting_id, member_id, clip_id, event_type, amount, confirmed_by, timestamp, prev_hash, entry_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (meeting_id, member_id, clip_id, event_type, float(amount), confirmed_by, timestamp, prev_hash, entry_hash))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def verify_chain(meeting_id: int, db_path: str = DB_PATH) -> dict:
    """
    Loop through entries sequentially. Verify stored_prev == expected_prev and
    recompute compute_entry_hash(...) == stored_hash.
    Return {"valid": True, "broken_at_entry_id": None} or
    {"valid": False, "broken_at_entry_id": <id>, "member": <name>, "reason": <reason>}.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            le.id, le.meeting_id, le.member_id, le.clip_id, le.event_type, 
            le.amount, le.confirmed_by, le.timestamp, le.prev_hash, le.entry_hash,
            ac.clip_hash, m.name as member_name
        FROM ledger_entries le
        JOIN audio_clips ac ON le.clip_id = ac.id
        JOIN members m ON le.member_id = m.id
        WHERE le.meeting_id = ?
        ORDER BY le.id ASC;
    """, (meeting_id,))
    entries = cursor.fetchall()
    conn.close()

    expected_prev = GENESIS_HASH

    for entry in entries:
        e_id = entry["id"]
        stored_prev = entry["prev_hash"]
        stored_hash = entry["entry_hash"]
        member_name = entry["member_name"]
        clip_hash = entry["clip_hash"]
        event_type = entry["event_type"]
        amount = entry["amount"]
        confirmed_by = entry["confirmed_by"]
        timestamp = entry["timestamp"]
        m_id = entry["meeting_id"]
        mem_id = entry["member_id"]

        # Check 1: prev_hash continuity
        if stored_prev != expected_prev:
            return {
                "valid": False,
                "broken_at_entry_id": e_id,
                "member": member_name,
                "reason": f"Previous hash pointer mismatch: Expected {expected_prev[:12]}..., got {stored_prev[:12]}..."
            }

        # Check 2: Content integrity
        recomputed = compute_entry_hash(
            prev_hash=stored_prev,
            meeting_id=m_id,
            member_id=mem_id,
            clip_hash=clip_hash,
            event_type=event_type,
            amount=amount,
            confirmed_by=confirmed_by,
            timestamp=timestamp
        )

        if recomputed != stored_hash:
            return {
                "valid": False,
                "broken_at_entry_id": e_id,
                "member": member_name,
                "reason": f"Block content tampering detected: Stored hash {stored_hash[:12]}... does not match recalculated hash {recomputed[:12]}..."
            }

        expected_prev = stored_hash

    return {"valid": True, "broken_at_entry_id": None}

def calculate_derived_balances(meeting_id: int, db_path: str = DB_PATH) -> dict:
    """
    Dynamically compute savings (thrift) and outstanding debt (loan_disbursement - repayment)
    per member from the ledger rows.
    """
    all_members = get_members(db_path)
    balances = {
        m["name"]: {
            "member_id": m["id"],
            "role": m["role"],
            "savings": 0.0,
            "loan_disbursed": 0.0,
            "repaid": 0.0,
            "fines": 0.0,
            "debt": 0.0
        }
        for m in all_members
    }

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT le.event_type, le.amount, m.name
        FROM ledger_entries le
        JOIN members m ON le.member_id = m.id
        WHERE le.meeting_id = ?;
    """, (meeting_id,))
    rows = cursor.fetchall()
    conn.close()

    total_thrift = 0.0
    total_disbursed = 0.0
    total_repaid = 0.0
    total_fines = 0.0

    for row in rows:
        name = row["name"]
        ev = row["event_type"]
        amt = float(row["amount"])

        if name not in balances:
            balances[name] = {
                "member_id": None,
                "role": "member",
                "savings": 0.0,
                "loan_disbursed": 0.0,
                "repaid": 0.0,
                "fines": 0.0,
                "debt": 0.0
            }

        if ev == "thrift":
            balances[name]["savings"] += amt
            total_thrift += amt
        elif ev == "loan_disbursement":
            balances[name]["loan_disbursed"] += amt
            balances[name]["debt"] += amt
            total_disbursed += amt
        elif ev == "repayment":
            balances[name]["repaid"] += amt
            balances[name]["debt"] = max(0.0, balances[name]["debt"] - amt)
            total_repaid += amt
        elif ev == "fine":
            balances[name]["fines"] += amt
            total_fines += amt

    return {
        "meeting_id": meeting_id,
        "members": balances,
        "summary": {
            "total_savings": total_thrift,
            "total_disbursed": total_disbursed,
            "total_repaid": total_repaid,
            "total_outstanding_debt": total_disbursed - total_repaid,
            "total_fines": total_fines
        }
    }

def validate_loan_confirmation(event_type: str, confirmed_by_role: str) -> tuple:
    """
    Per SabhaLedger governance rule:
    Loan disbursements cannot be confirmed by the Secretary alone.
    Returns (is_valid: bool, error_message: str or None).
    """
    if event_type == "loan_disbursement" and confirmed_by_role and confirmed_by_role.lower() == "secretary":
        return False, "Governance Rule: Loan disbursements must be confirmed by a member or president, not the Secretary alone."
    return True, None

def validate_transaction_logic(meeting_id: int, member_name: str, event_type: str,
                               amount: float, confirmed_by_name: str, confirmed_by_role: str,
                               db_path: str = DB_PATH) -> tuple:
    """
    Validates logical business and accounting rules before committing a ledger entry:
    - Rule D (Positive Amount): amount > 0.
    - Rule B (No Self-Confirmation): member_name != confirmed_by_name.
    - Rule C (Two-Person Loan Rule): loan_disbursement cannot be confirmed by secretary alone.
    - Rule A (Loan Repayment Cannot Exceed Outstanding Debt):
      repayment requires outstanding_debt > 0 and amount <= outstanding_debt.

    Returns (is_valid: bool, error_message: str or None).
    """
    # Rule D: Positive Amount Check
    if amount is None or amount <= 0:
        return False, "⚠️ തുക പൂജ്യത്തേക്കാൾ കൂടുതലായിരിക്കണം (Please enter a valid amount greater than ₹0.00)."

    # Rule B: No Self-Confirmation
    if member_name and confirmed_by_name and member_name.strip().lower() == confirmed_by_name.strip().lower():
        return False, "⚠️ നിയമം (Governance Rule): ഇടപാട് നടത്തുന്ന അംഗത്തിന് സ്വയം സാക്ഷ്യപ്പെടുത്താൻ കഴിയില്ല (A member cannot confirm their own transaction. Please select another member/officer)."

    # Rule C: Two-Person Loan Governance Rule
    if event_type == "loan_disbursement" and confirmed_by_role and confirmed_by_role.strip().lower() == "secretary":
        return False, "⚠️ വായ്പാ തുക സെക്രട്ടറി മാത്രം നൽകാൻ പാടില്ല. പ്രസിഡന്റോ മറ്റൊരു അംഗമോ കൂടി ഒപ്പിടണം (Governance Rule: Loan disbursements must be confirmed by a member or president, not the Secretary alone)."

    # Rule A: Loan Repayment Cannot Exceed Outstanding Debt
    # Rule E: Thrift-to-Loan Eligibility — member must have positive thrift savings before receiving a loan
    if event_type in ("repayment", "loan_disbursement"):
        balances_data = calculate_derived_balances(meeting_id, db_path=db_path)
        member_data = balances_data.get("members", {}).get(member_name, {})

        if event_type == "repayment":
            outstanding_debt = float(member_data.get("debt", 0.0))

            if outstanding_debt <= 0:
                return False, f"⚠️ ലോജിക് പിശക് (Logical Error): {member_name}-ന് നിലവിൽ തിരിച്ചടയ്ക്കാൻ വായ്പാ ബാക്കിയില്ല (Current Outstanding Loan is ₹0.00). ആദ്യം വായ്പ (Loan Disbursement) രേഖപ്പെടുത്തുക."

            if amount > outstanding_debt:
                return False, f"⚠️ അധിക തിരിച്ചടവ് (Excess Repayment): {member_name}-ന്റെ ബാക്കിയുള്ള വായ്പ ₹{outstanding_debt:.2f} മാത്രമാണ്. ₹{amount:.2f} തിരിച്ചടയ്ക്കാൻ സാധ്യമല്ല."

        elif event_type == "loan_disbursement":
            # Rule E: Block loan if member has zero thrift savings
            member_savings = float(member_data.get("savings", 0.0))
            if member_savings <= 0:
                return False, (
                    "⚠️ വായ്പാ യോഗ്യതാ നിയമം (Loan Eligibility Rule): "
                    "സമ്പാദ്യം (Thrift) ഇല്ലാത്ത അംഗത്തിന് വായ്പ അനുവദിക്കാൻ കഴിയില്ല. "
                    "ആദ്യം സമ്പാദ്യം രേഖപ്പെടുത്തുക."
                )

    return True, None

def reset_ledger(meeting_id: int, db_path: str = DB_PATH) -> dict:
    """
    Clears all ledger entries and audio clips for the specified meeting,
    resetting the session back to Genesis (Block #0) and resetting SQLite auto-increment.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ledger_entries WHERE meeting_id = ?;", (meeting_id,))
    deleted_entries = cursor.rowcount
    cursor.execute("DELETE FROM audio_clips WHERE meeting_id = ?;", (meeting_id,))
    deleted_clips = cursor.rowcount
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('ledger_entries', 'audio_clips');")
    conn.commit()
    conn.close()
    return {
        "meeting_id": meeting_id,
        "deleted_entries": deleted_entries,
        "deleted_clips": deleted_clips
    }

def delete_latest_ledger_entry(meeting_id: int, db_path: str = DB_PATH) -> dict:
    """
    Safely removes the most recent ledger entry (the tail of the hash chain) for a meeting.
    Because only the latest block is removed, the cryptographic hash chain of all preceding
    blocks remains 100% intact and valid.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, member_id, clip_id, event_type, amount FROM ledger_entries WHERE meeting_id = ? ORDER BY id DESC LIMIT 1;",
        (meeting_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "ഒഴിവാക്കാൻ ഇടപാടുകളൊന്നുമില്ല (No entries found in ledger)."}

    entry_id = row["id"]
    amount = row["amount"]
    ev_type = row["event_type"]

    cursor.execute("DELETE FROM ledger_entries WHERE id = ?;", (entry_id,))

    # If table is now completely empty, reset sqlite_sequence so next entry is ID 1
    cursor.execute("SELECT COUNT(*) FROM ledger_entries WHERE meeting_id = ?;", (meeting_id,))
    if cursor.fetchone()[0] == 0:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('ledger_entries', 'audio_clips');")

    conn.commit()
    conn.close()

    return {
        "success": True,
        "deleted_entry_id": entry_id,
        "amount": amount,
        "event_type": ev_type
    }

