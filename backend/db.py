import sqlite3
import uuid
from datetime import datetime, timezone
import os
import json  # Needed to serialize event_data to JSON strings

DB_PATH = os.path.join(os.path.dirname(__file__), "kindling.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            sender      TEXT NOT NULL CHECK (sender IN ('user', 'assistant')),
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        -- [REVIEW 2] TCP-41: Telemetry events table
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            event_data  TEXT,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id             TEXT PRIMARY KEY,
            email          TEXT NOT NULL UNIQUE,
            password_hash  TEXT NOT NULL,
            created_at     TEXT NOT NULL
        );

        -- Career tree AI-naming layer cache (Phase 2). Most generated
        -- strings (field names, career short titles, "try it" text)
        -- are session-independent — the same real occupation/task
        -- always gets the same real treatment, so they're cached
        -- once and reused by every user. "why it's connected" is the
        -- one kind that depends on a specific user's real evidence,
        -- so its cache_key includes a hash of that evidence — see
        -- ai_core/tree_naming.py.
        CREATE TABLE IF NOT EXISTS generated_strings (
            cache_key   TEXT PRIMARY KEY,
            kind        TEXT NOT NULL,
            value       TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        -- Reflection's "Your take" notes. One row per saved note,
        -- real account-scoped (not session-scoped like everything
        -- else) so a preference set on one thread still applies when
        -- the student opens a different thread's Career Graph later.
        CREATE TABLE IF NOT EXISTS reflection_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            note_text   TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        -- One row per individual extracted+resolved preference
        -- (a single hidden field, the one focus field, one pattern
        -- adjustment, one "new to them" mention) so a single chip's
        -- x can delete just that preference without touching the
        -- rest of its parent note, and deleting the note cascades to
        -- every preference it produced.
        CREATE TABLE IF NOT EXISTS reflection_preferences (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id     INTEGER NOT NULL,
            user_id     TEXT NOT NULL,
            kind        TEXT NOT NULL CHECK (kind IN ('hide_field', 'focus_field', 'pattern_adjust', 'new_to_them')),
            label       TEXT NOT NULL,
            extra       TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES reflection_notes(id)
        );
    """)

    # sessions already existed (with real data) before user_id was
    # added, so CREATE TABLE IF NOT EXISTS above never adds it to an
    # existing database — migrate explicitly, once, only if missing.
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "user_id" not in existing_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")

    if "title" not in existing_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN title TEXT")

    if "pinned" not in existing_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")

    if "pinned_at" not in existing_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN pinned_at TEXT")

    existing_user_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "name" not in existing_user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN name TEXT")

    conn.commit()
    conn.close()

def create_session(user_id: str | None = None) -> str:
    """
    Generates a new session_id, saves it to the DB, and returns the
    ID. user_id is nullable — anonymous sessions (no auth token
    sent) keep working exactly as before, with NULL here.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (session_id, created_at, user_id) VALUES (?, ?, ?)",
        (session_id, now, user_id)
    )
    conn.commit()
    conn.close()
    return session_id


def get_sessions_for_user(user_id: str) -> list[dict]:
    """
    Returns every REAL session belonging to a signed-in user (at
    least one real user message — a "New thread" click that was
    never actually used doesn't count as a thread), newest first,
    with its generated title (NULL until enough turns have happened
    to generate one — the caller decides the "New conversation"
    placeholder) and pin state.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT s.session_id, s.created_at, s.title, s.pinned, s.pinned_at
        FROM sessions s
        WHERE s.user_id = ?
          AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.session_id AND m.sender = 'user')
        ORDER BY s.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()

    return [dict(row) for row in rows]


def set_session_title(session_id: str, title: str) -> None:
    conn = get_db()
    conn.execute("UPDATE sessions SET title = ? WHERE session_id = ?", (title, session_id))
    conn.commit()
    conn.close()


def get_session_title(session_id: str) -> str | None:
    conn = get_db()
    row = conn.execute("SELECT title FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return row["title"] if row else None


def get_session_user_id(session_id: str) -> str | None:
    conn = get_db()
    row = conn.execute("SELECT user_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return row["user_id"] if row else None


def count_pinned_sessions(user_id: str) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM sessions WHERE user_id = ? AND pinned = 1", (user_id,)
    ).fetchone()
    conn.close()
    return row["c"]


def set_session_pinned(session_id: str, pinned: bool, pinned_at: str | None) -> None:
    conn = get_db()
    conn.execute(
        "UPDATE sessions SET pinned = ?, pinned_at = ? WHERE session_id = ?",
        (1 if pinned else 0, pinned_at, session_id)
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str) -> None:
    """Removes a thread completely: its messages, its events (real
    scores, node_time, trait decisions — everything Inference,
    Career Graph, and Reflection read is session_id-scoped and
    stored in these two tables, nothing duplicated elsewhere), and
    the session row itself."""
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def delete_empty_sessions_for_user(user_id: str, exclude_session_id: str | None = None) -> int:
    """
    Real cleanup for abandoned "New thread" clicks: sessions with a
    user_id but zero real user messages. Called opportunistically
    right before a new session is created, so the DB itself never
    accumulates empty rows — not just hiding them in the list.
    Returns how many were removed.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT s.session_id FROM sessions s
        WHERE s.user_id = ?
          AND s.session_id != COALESCE(?, '')
          AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.session_id AND m.sender = 'user')
    """, (user_id, exclude_session_id)).fetchall()

    for row in rows:
        sid = row["session_id"]
        conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM events WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))

    conn.commit()
    conn.close()
    return len(rows)


def create_user(email: str, password_hash: str, name: str | None = None) -> str | None:
    """
    Creates a new user with an already-hashed password. Returns
    the new user's id, or None if the email is already taken.
    Email is normalized (trimmed + lowercased) so the same
    address can't be registered twice under different casing.
    name is optional and stored exactly as given (already
    trimmed/validated by the caller) - NULL if not provided.
    """
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    normalized_email = email.strip().lower()

    conn = get_db()

    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, created_at, name) VALUES (?, ?, ?, ?, ?)",
            (user_id, normalized_email, password_hash, now, name)
        )
        conn.commit()
        return user_id

    except sqlite3.IntegrityError:
        return None

    finally:
        conn.close()


def get_user_by_id(user_id: str) -> sqlite3.Row | None:
    """Looks up a user by id (the value used as their auth token)."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    return row


def get_user_by_email(email: str) -> sqlite3.Row | None:
    """Looks up a user by email (case-insensitive)."""
    normalized_email = email.strip().lower()

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (normalized_email,)
    ).fetchone()
    conn.close()

    return row


def add_message(session_id: str, sender: str, content: str) -> None:
    """Saves a single message (from 'user' or 'assistant') to the DB."""
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (session_id, sender, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, sender, content, now)
    )
    conn.commit()
    conn.close()

def get_messages(session_id: str) -> list[dict]:
    """Retrieves all messages for a session formatted for the LLM."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT sender, content FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    formatted_messages = []
    for row in rows:
        formatted_messages.append({
            "role": "user" if row["sender"] == "user" else "assistant",
            "content": row["content"]
        })
        
    return formatted_messages

def count_user_messages(session_id: str) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ? AND sender = 'user'",
        (session_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]

def session_exists(session_id: str) -> bool:
    """Returns True if the session_id exists in SQLite, False otherwise."""
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM sessions WHERE session_id = ?", 
        (session_id,)
    ).fetchone()
    conn.close()
    return row is not None


# =====================================================================
# [REVIEW 2] TELEMETRY & DASHBOARD DB FUNCTIONS
# TCP-41, TCP-52, TCP-53, TCP-54
# =====================================================================

def log_event(session_id: str, event_type: str, event_data: dict = None) -> None:
    """
    TCP-41: Logs an interaction event into the events table.
    e.g., event_type='session_started', 'message_sent', 'career_card_clicked'
    """
    now = datetime.now(timezone.utc).isoformat()
    data_str = json.dumps(event_data) if event_data else "{}"

    conn = get_db()
    conn.execute(
        "INSERT INTO events (session_id, event_type, event_data, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, event_type, data_str, now)
    )
    conn.commit()
    conn.close()


def get_latest_inference_scores(session_id: str) -> dict | None:
    """
    Retrieves the most recent computed or user-updated 6D scores for a session from SQLite events table.
    Checks 'profile_updated' first (if user edited scores), then 'score_computed'.
    """
    conn = get_db()
    cursor = conn.execute("""
        SELECT event_data FROM events 
        WHERE session_id = ? AND event_type IN ('score_computed', 'profile_updated')
        ORDER BY id DESC LIMIT 1
    """, (session_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row["event_data"]:
        try:
            return json.loads(row["event_data"])
        except Exception:
            return None
    return None


def get_latest_trait_decisions_for_sessions(session_ids: list[str]) -> dict:
    """
    Same real trait_accepted/trait_rejected folding as
    get_latest_trait_decisions, generalized to several sessions at
    once (Connect Threads' combined mode) - ordered by the events
    table's own global id, so "latest" is true chronological order
    across sessions, not just last-session-wins.
    """
    if not session_ids:
        return {}

    conn = get_db()
    placeholders = ",".join("?" for _ in session_ids)
    rows = conn.execute(f"""
        SELECT event_type, event_data FROM events
        WHERE session_id IN ({placeholders}) AND event_type IN ('trait_accepted', 'trait_rejected')
        ORDER BY id ASC
    """, tuple(session_ids)).fetchall()
    conn.close()

    decisions = {}
    for row in rows:
        try:
            data = json.loads(row["event_data"])
        except Exception:
            continue
        trait = data.get("trait")
        if trait:
            decisions[trait] = "accept" if row["event_type"] == "trait_accepted" else "reject"

    return decisions


def get_latest_trait_decisions(session_id: str) -> dict:
    """
    The most recent accept/reject decision per RIASEC trait, from the
    real trait_accepted/trait_rejected events POST /api/user/trait/
    decision already logs — there's no dedicated calibration table,
    so this reads the same events table score/timeline queries use.
    Returns {trait: "accept" | "reject"}; a trait never decided on
    is simply absent, not a fabricated "neutral" entry.
    """
    return get_latest_trait_decisions_for_sessions([session_id])


def get_cached_string(cache_key: str) -> str | None:
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM generated_strings WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def set_cached_string(cache_key: str, kind: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO generated_strings (cache_key, kind, value, created_at) VALUES (?, ?, ?, ?)",
        (cache_key, kind, value, now)
    )
    conn.commit()
    conn.close()


def get_dashboard_metrics() -> dict:
    """
    TCP-52: Computes aggregated analytics for the admin/dashboard view.
    Returns counts for total sessions, total user messages, total events, and breakdown by event type.
    """
    conn = get_db()

    total_sessions = conn.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()["cnt"]

    total_user_messages = conn.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE sender = 'user'"
    ).fetchone()["cnt"]

    total_events = conn.execute("SELECT COUNT(*) AS cnt FROM events").fetchone()["cnt"]

    event_rows = conn.execute("""
        SELECT event_type, COUNT(*) AS cnt
        FROM events
        GROUP BY event_type
        ORDER BY cnt DESC
    """).fetchall()
    event_breakdown = {row["event_type"]: row["cnt"] for row in event_rows}

    recent_rows = conn.execute("""
        SELECT session_id, created_at
        FROM sessions
        ORDER BY created_at DESC
        LIMIT 5
    """).fetchall()
    recent_sessions = [{"session_id": r["session_id"], "created_at": r["created_at"]} for r in recent_rows]

    conn.close()

    return {
        "total_sessions": total_sessions,
        "total_user_messages": total_user_messages,
        "total_events": total_events,
        "event_breakdown": event_breakdown,
        "recent_sessions": recent_sessions,
    }


def get_session_timeline(session_id: str) -> list[dict]:
    """
    TCP-54: Returns an ordered, chronological timeline combining messages and events for a session.
    """
    return get_timeline_for_sessions([session_id])


def get_timeline_for_sessions(session_ids: list[str]) -> list[dict]:
    """
    Same timeline shape as get_session_timeline, across several real
    sessions at once (Connect Threads' combined mode) - one merged,
    chronologically ordered timeline, not several separate ones.
    """
    if not session_ids:
        return []

    conn = get_db()
    placeholders = ",".join("?" for _ in session_ids)
    cursor = conn.execute(f"""
        SELECT 'message' AS item_type, sender AS detail, content AS data, timestamp
        FROM messages WHERE session_id IN ({placeholders})
        UNION ALL
        SELECT 'event' AS item_type, event_type AS detail, event_data AS data, timestamp
        FROM events WHERE session_id IN ({placeholders})
        ORDER BY timestamp ASC
    """, tuple(session_ids) * 2)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_combined_messages_for_user(user_id: str) -> list[dict]:
    """
    Every real message across all of this user's real sessions
    (get_sessions_for_user's own "at least one real user message"
    definition), oldest session first and messages within each
    session in their own real order - one continuous transcript, the
    same {"role", "content"} shape get_messages() already returns per
    session, ready for score_session() unchanged.
    """
    sessions_newest_first = get_sessions_for_user(user_id)
    combined = []
    for session in reversed(sessions_newest_first):
        combined.extend(get_messages(session["session_id"]))
    return combined


def get_user_content_fingerprint(user_id: str) -> str:
    """
    Changes whenever any of this user's real sessions gets a new
    message - used as part of the combined-mode cache key so a stale
    "all threads" result is never served after new real content
    exists (see main.py's USER_SCORE_CACHE/USER_TREE_CACHE).
    """
    conn = get_db()
    row = conn.execute("""
        SELECT COUNT(*) AS cnt, COALESCE(MAX(m.id), 0) AS last_id
        FROM messages m
        JOIN sessions s ON s.session_id = m.session_id
        WHERE s.user_id = ?
    """, (user_id,)).fetchone()
    conn.close()
    return f"{row['cnt']}:{row['last_id']}"


def get_field_summary() -> dict:
    """
    TCP-53: Returns event frequencies and distribution across telemetry types for dashboard charts.
    """
    conn = get_db()
    cursor = conn.execute("""
        SELECT event_type, COUNT(*) AS total_count, MAX(timestamp) AS last_seen
        FROM events
        GROUP BY event_type
        ORDER BY total_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return {r["event_type"]: {"count": r["total_count"], "last_seen": r["last_seen"]} for r in rows}


# =====================================================================
# REFLECTION NOTES ("Your take") — real per-user preferences
# =====================================================================

def create_reflection_note(user_id: str, session_id: str, note_text: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO reflection_notes (user_id, session_id, note_text, created_at) VALUES (?, ?, ?, ?)",
        (user_id, session_id, note_text, now)
    )
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return note_id


def add_reflection_preference(note_id: int, user_id: str, kind: str, label: str, extra: dict | None = None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO reflection_preferences (note_id, user_id, kind, label, extra, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, user_id, kind, label, json.dumps(extra) if extra is not None else None, now)
    )
    pref_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pref_id


def get_reflection_notes_for_user(user_id: str) -> list[dict]:
    """Every saved note for this account, newest first, each with its
    own resolved preferences attached (so the UI never has to stitch
    the two tables together itself)."""
    conn = get_db()
    note_rows = conn.execute(
        "SELECT id, session_id, note_text, created_at FROM reflection_notes WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    ).fetchall()
    pref_rows = conn.execute(
        "SELECT id, note_id, kind, label, extra, created_at FROM reflection_preferences WHERE user_id = ? ORDER BY id ASC",
        (user_id,)
    ).fetchall()
    conn.close()

    prefs_by_note = {}
    for row in pref_rows:
        prefs_by_note.setdefault(row["note_id"], []).append({
            "id": row["id"],
            "kind": row["kind"],
            "label": row["label"],
            "extra": json.loads(row["extra"]) if row["extra"] else None,
            "created_at": row["created_at"],
        })

    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "note_text": row["note_text"],
            "created_at": row["created_at"],
            "preferences": prefs_by_note.get(row["id"], []),
        }
        for row in note_rows
    ]


def get_active_reflection_preferences(user_id: str) -> list[dict]:
    """Flat list of every currently-active preference for this user
    (no note grouping) — what career_tree.py and the pattern-adjust
    undo logic actually read to apply/reverse effects."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, note_id, kind, label, extra, created_at FROM reflection_preferences WHERE user_id = ? ORDER BY id ASC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "note_id": row["note_id"],
            "kind": row["kind"],
            "label": row["label"],
            "extra": json.loads(row["extra"]) if row["extra"] else None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_reflection_preference(pref_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT id, note_id, user_id, kind, label, extra, created_at FROM reflection_preferences WHERE id = ?",
        (pref_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"], "note_id": row["note_id"], "user_id": row["user_id"],
        "kind": row["kind"], "label": row["label"],
        "extra": json.loads(row["extra"]) if row["extra"] else None,
        "created_at": row["created_at"],
    }


def get_preferences_for_note(note_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, note_id, user_id, kind, label, extra, created_at FROM reflection_preferences WHERE note_id = ?",
        (note_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": row["id"], "note_id": row["note_id"], "user_id": row["user_id"],
            "kind": row["kind"], "label": row["label"],
            "extra": json.loads(row["extra"]) if row["extra"] else None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_reflection_note_owner(note_id: int) -> str | None:
    conn = get_db()
    row = conn.execute("SELECT user_id FROM reflection_notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    return row["user_id"] if row else None


def delete_reflection_preference(pref_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM reflection_preferences WHERE id = ?", (pref_id,))
    conn.commit()
    conn.close()


def delete_reflection_note(note_id: int) -> None:
    """Cascades: removes every preference this note produced too."""
    conn = get_db()
    conn.execute("DELETE FROM reflection_preferences WHERE note_id = ?", (note_id,))
    conn.execute("DELETE FROM reflection_notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    test_session_id = create_session()
    add_message(test_session_id, "assistant", "What have you been curious about lately?")
    add_message(test_session_id, "user", "I've been tinkering with mechanical keyboards.")
    log_event(test_session_id, "session_started", {"source": "test_script"})
    print(f"Created & verified session: {test_session_id}")
    print("\n[REVIEW 2 TEST] Dashboard Metrics:")
    print(json.dumps(get_dashboard_metrics(), indent=2))