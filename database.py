import sqlite3
import secrets
from contextlib import contextmanager
from datetime import datetime
import pytz

DB_PATH = "modern_bot.db"
TZ = pytz.timezone("Asia/Tashkent")

def get_now():
    return datetime.now(TZ)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                invite_code TEXT UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id INTEGER,
                group_id INTEGER,
                PRIMARY KEY (user_id, group_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                teacher TEXT,
                meeting_link TEXT,
                start_time TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sent_reminders (
                lesson_id INTEGER,
                reminder_type TEXT,
                PRIMARY KEY (lesson_id, reminder_type)
            )
        """)

# --- Groups ---
def create_group(name: str, owner_id: int):
    code = secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO groups (name, invite_code, owner_id) VALUES (?, ?, ?)",
            (name, code, owner_id)
        )
        group_id = cur.lastrowid
        # Admin guruhiga avto obuna bo'ladi
        conn.execute("INSERT OR IGNORE INTO subscribers (user_id, group_id) VALUES (?, ?)", (owner_id, group_id))
        return conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()

def get_user_owned_groups(owner_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE owner_id = ?", (owner_id,)).fetchall()

def get_user_subscribed_groups(user_id: int):
    with get_db() as conn:
        return conn.execute("""
            SELECT g.* FROM groups g
            JOIN subscribers s ON s.group_id = g.id
            WHERE s.user_id = ?
        """, (user_id,)).fetchall()

def get_group(group_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()

def get_group_by_code(code: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE invite_code = ?", (code,)).fetchone()

def delete_group(group_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.execute("DELETE FROM subscribers WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM lessons WHERE group_id = ?", (group_id,))

# --- Subscribers ---
def add_subscriber(user_id: int, group_id: int):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO subscribers (user_id, group_id) VALUES (?, ?)", (user_id, group_id))

def get_subscribers(group_id: int):
    with get_db() as conn:
        rows = conn.execute("SELECT user_id FROM subscribers WHERE group_id = ?", (group_id,)).fetchall()
        return [r["user_id"] for r in rows]

# --- Lessons ---
def add_lesson(group_id: int, title: str, teacher: str, meeting_link: str, start_time_iso: str):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO lessons (group_id, title, teacher, meeting_link, start_time)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, title, teacher, meeting_link, start_time_iso))

def cleanup_lessons():
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("DELETE FROM lessons WHERE start_time < ?", (now_str,))

def get_upcoming_lessons_for_group(group_id: int):
    cleanup_lessons()
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        return conn.execute("""
            SELECT * FROM lessons WHERE group_id = ? AND start_time >= ? ORDER BY start_time ASC
        """, (group_id, now_str)).fetchall()

def get_all_future_lessons():
    cleanup_lessons()
    with get_db() as conn:
        return conn.execute("SELECT * FROM lessons ORDER BY start_time ASC").fetchall()

def delete_lesson(lesson_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))

# --- Reminders ---
def was_reminder_sent(lesson_id: int, r_type: str):
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM sent_reminders WHERE lesson_id = ? AND reminder_type = ?", (lesson_id, r_type)).fetchone()
        return row is not None

def mark_reminder_sent(lesson_id: int, r_type: str):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO sent_reminders (lesson_id, reminder_type) VALUES (?, ?)", (lesson_id, r_type))
