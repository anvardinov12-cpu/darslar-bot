"""
Ma'lumotlar bazasi: guruhlar, darslar, obunachilar, yuborilgan eslatmalar.
O'zbekiston vaqti (UTC+5) va avto-o'chirish mexanizmi bilan.
"""
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
import pytz

DB_PATH = "bot_data.db"
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
                owner_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id INTEGER,
                group_id INTEGER,
                username TEXT,
                first_name TEXT,
                active INTEGER DEFAULT 1,
                subscribed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, group_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                teacher TEXT,
                subject TEXT,
                start_time TEXT NOT NULL,
                duration_min INTEGER DEFAULT 60,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sent_reminders (
                lesson_id INTEGER,
                reminder_type TEXT,
                PRIMARY KEY (lesson_id, reminder_type)
            )
        """)

# ---------------------- Groups ----------------------

def create_group(name: str, owner_id: int):
    code = secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO groups (name, invite_code, owner_id) VALUES (?, ?, ?)",
            (name, code, owner_id),
        )
        group_id = cur.lastrowid
        return conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()

def update_group_name(group_id: int, new_name: str):
    with get_db() as conn:
        conn.execute("UPDATE groups SET name = ? WHERE id = ?", (new_name, group_id))

def delete_group(group_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.execute("DELETE FROM subscribers WHERE group_id = ?", (group_id,))
        lessons = conn.execute("SELECT id FROM lessons WHERE group_id = ?", (group_id,)).fetchall()
        for l in lessons:
            conn.execute("DELETE FROM sent_reminders WHERE lesson_id = ?", (l["id"],))
        conn.execute("DELETE FROM lessons WHERE group_id = ?", (group_id,))

def get_group_by_code(code: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE invite_code = ?", (code,)).fetchone()

def get_group_by_id(group_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()

def get_groups_owned_by(owner_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM groups WHERE owner_id = ? ORDER BY id ASC", (owner_id,)
        ).fetchall()

def get_all_groups():
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups ORDER BY id ASC").fetchall()

# ---------------------- Subscribers ----------------------

def add_subscriber(user_id, group_id, username, first_name):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO subscribers (user_id, group_id, username, first_name, active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, group_id) DO UPDATE SET active = 1, username = excluded.username
        """, (user_id, group_id, username, first_name))

def remove_subscriber(user_id, group_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE subscribers SET active = 0 WHERE user_id = ? AND group_id = ?",
            (user_id, group_id),
        )

def get_active_subscribers(group_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT user_id FROM subscribers WHERE group_id = ? AND active = 1", (group_id,)
        ).fetchall()
        return [r["user_id"] for r in rows]

def get_user_groups(user_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT g.* FROM groups g
            JOIN subscribers s ON s.group_id = g.id
            WHERE s.user_id = ? AND s.active = 1
            ORDER BY g.name
        """, (user_id,)).fetchall()
        return rows

def count_subscribers(group_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM subscribers WHERE group_id = ? AND active = 1", (group_id,)
        ).fetchone()
        return row["c"]

# ---------------------- Lessons ----------------------

def add_lesson(group_id, title, teacher, subject, start_time_iso, duration_min=60):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO lessons (group_id, title, teacher, subject, start_time, duration_min)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (group_id, title, teacher, subject, start_time_iso, duration_min))
        return cur.lastrowid

def cleanup_expired_lessons():
    """O'tib ketgan darslarni avtomatik o'chirish (start_time + duration_min dan o'tgan bo'lsa)"""
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        expired = conn.execute(
            "SELECT id FROM lessons WHERE start_time < ?", (now_str,)
        ).fetchall()
        for row in expired:
            conn.execute("DELETE FROM sent_reminders WHERE lesson_id = ?", (row["id"],))
            conn.execute("DELETE FROM lessons WHERE id = ?", (row["id"],))

def get_upcoming_lessons(group_id, limit=50):
    cleanup_expired_lessons()
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        return conn.execute("""
            SELECT * FROM lessons
            WHERE group_id = ? AND start_time >= ?
            ORDER BY start_time ASC
            LIMIT ?
        """, (group_id, now_str, limit)).fetchall()

def get_all_future_lessons():
    cleanup_expired_lessons()
    return get_active_lessons_for_reminders()

def get_active_lessons_for_reminders():
    with get_db() as conn:
        return conn.execute("SELECT * FROM lessons ORDER BY start_time ASC").fetchall()

def get_lesson(lesson_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()

def delete_lesson(lesson_id):
    with get_db() as conn:
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        conn.execute("DELETE FROM sent_reminders WHERE lesson_id = ?", (lesson_id,))

# ---------------------- Reminder tracking ----------------------

def was_reminder_sent(lesson_id, reminder_type):
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM sent_reminders WHERE lesson_id = ? AND reminder_type = ?",
            (lesson_id, reminder_type),
        ).fetchone()
        return row is not None

def mark_reminder_sent(lesson_id, reminder_type):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_reminders (lesson_id, reminder_type) VALUES (?, ?)",
            (lesson_id, reminder_type),
        )
