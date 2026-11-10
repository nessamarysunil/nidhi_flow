import os
import sqlite3
import datetime
from pathlib import Path

# Path to the SQLite database file
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sabhaledger.db")

def get_db_connection(db_path=DB_PATH):
    """Returns a SQLite connection with foreign keys enabled and row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path=DB_PATH, auto_seed: bool = True):
    """
    Initializes the database schema for SabhaLedger:
    - members
    - meetings
    - audio_clips
    - ledger_entries
    - db_meta (tracks initialization lifecycle)
    Auto-seeds the 5 default members only on first creation when auto_seed=True.
    Does NOT forcefully re-seed after clear_members() is called during a session.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. members table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        role TEXT DEFAULT 'member'
    );
    """)

    # 2. meetings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_date TEXT NOT NULL,
        status TEXT DEFAULT 'active'
    );
    """)

    # 3. audio_clips table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audio_clips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        clip_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
    );
    """)

    # 4. ledger_entries table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ledger_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        clip_id INTEGER NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN ('thrift', 'loan_disbursement', 'repayment', 'fine')),
        amount REAL NOT NULL,
        confirmed_by INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        entry_hash TEXT NOT NULL,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id),
        FOREIGN KEY (member_id) REFERENCES members(id),
        FOREIGN KEY (clip_id) REFERENCES audio_clips(id),
        FOREIGN KEY (confirmed_by) REFERENCES members(id)
    );
    """)

    # 5. db_meta table to track initialization state
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS db_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    conn.commit()

    # Check if database has been initialized before
    cursor.execute("SELECT value FROM db_meta WHERE key = 'initialized';")
    init_row = cursor.fetchone()

    if not init_row:
        # First-time database creation: seed initial members if auto_seed is True
        if auto_seed:
            cursor.execute("SELECT COUNT(*) FROM members;")
            if cursor.fetchone()[0] == 0:
                seed_members = [
                    ("Leela", "secretary"),
                    ("Radha", "president"),
                    ("Chitra", "member"),
                    ("Meera", "member"),
                    ("Suma", "member")
                ]
                cursor.executemany("INSERT INTO members (name, role) VALUES (?, ?);", seed_members)
                conn.commit()

        cursor.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES ('initialized', '1');")
        conn.commit()

    # Seed initial meeting for today if no active meeting exists
    cursor.execute("SELECT COUNT(*) FROM meetings WHERE status = 'active';")
    if cursor.fetchone()[0] == 0:
        today_str = datetime.date.today().isoformat()
        cursor.execute("INSERT INTO meetings (meeting_date, status) VALUES (?, 'active');", (today_str,))
        conn.commit()

    conn.close()

def get_members(db_path=DB_PATH):
    """Fetch all members as a list of dicts: [{'id': ..., 'name': ..., 'role': ...}]"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, role FROM members ORDER BY id ASC;")
    rows = cursor.fetchall()
    members = [dict(row) for row in rows]
    conn.close()
    return members

def get_active_meeting(db_path=DB_PATH):
    """Fetch the first active meeting, creating one for today if none exists."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, meeting_date, status FROM meetings WHERE status = 'active' ORDER BY id DESC LIMIT 1;")
    row = cursor.fetchone()
    if not row:
        today_str = datetime.date.today().isoformat()
        cursor.execute("INSERT INTO meetings (meeting_date, status) VALUES (?, 'active');", (today_str,))
        conn.commit()
        cursor.execute("SELECT id, meeting_date, status FROM meetings WHERE status = 'active' ORDER BY id DESC LIMIT 1;")
        row = cursor.fetchone()
    meeting = dict(row)
    conn.close()
    return meeting

def get_member_by_id(member_id, db_path=DB_PATH):
    """Fetch member details by ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, role FROM members WHERE id = ?;", (member_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def add_member(name: str, role: str = "member", db_path=DB_PATH):
    """
    Inserts a new member into members (INSERT OR IGNORE INTO members (name, role) VALUES (?, ?)).
    Returns the member dict.
    """
    name_clean = name.strip()
    role_clean = role.strip().lower()
    if not name_clean:
        return None
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO members (name, role) VALUES (?, ?);", (name_clean, role_clean))
    conn.commit()
    cursor.execute("SELECT id, name, role FROM members WHERE name = ?;", (name_clean,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def clear_members(db_path=DB_PATH):
    """
    Deletes all rows from members (and resets ledger_entries / audio_clips to prevent orphaned foreign keys).
    Also resets sqlite_sequence counters so new members start at ID 1.
    Ensures db_meta marks the database as initialized so init_db() does not forcefully re-seed.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ledger_entries;")
    cur.execute("DELETE FROM audio_clips;")
    cur.execute("DELETE FROM members;")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('ledger_entries', 'audio_clips', 'members');")
    cur.execute("CREATE TABLE IF NOT EXISTS db_meta (key TEXT PRIMARY KEY, value TEXT);")
    cur.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES ('initialized', '1');")
    conn.commit()
    conn.close()

def reset_demo_ledger(db_path=DB_PATH):
    """
    Clears all ledger entries and audio clips, resets the SQLite auto-increment
    counter so new entries start cleanly at ID 1, and ensures no orphan records remain.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ledger_entries;")
    cur.execute("DELETE FROM audio_clips;")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('ledger_entries', 'audio_clips');")
    conn.commit()
    conn.close()

clear_ledger = reset_demo_ledger

def load_sample_members(db_path=DB_PATH):
    """
    Inserts the 5 sample members:
    Leela (secretary), Radha (president), Chitra (member), Meera (member), Suma (member)
    using INSERT OR IGNORE.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    samples = [
        ("Leela", "secretary"),
        ("Radha", "president"),
        ("Chitra", "member"),
        ("Meera", "member"),
        ("Suma", "member")
    ]
    for name, role in samples:
        cur.execute("INSERT OR IGNORE INTO members (name, role) VALUES (?, ?);", (name, role))
    cur.execute("CREATE TABLE IF NOT EXISTS db_meta (key TEXT PRIMARY KEY, value TEXT);")
    cur.execute("INSERT OR REPLACE INTO db_meta (key, value) VALUES ('initialized', '1');")
    conn.commit()
    conn.close()

# Both naming conventions supported
seed_sample_members = load_sample_members

__all__ = [
    "DB_PATH",
    "get_db_connection",
    "init_db",
    "get_members",
    "get_active_meeting",
    "get_member_by_id",
    "add_member",
    "clear_members",
    "reset_demo_ledger",
    "clear_ledger",
    "load_sample_members",
    "seed_sample_members"
]
