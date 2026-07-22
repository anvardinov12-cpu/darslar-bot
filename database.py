"""
Ma'lumotlar bazasi: guruhlar, darslar, obunachilar, yuborilgan eslatmalar.
Endi bitta bot ko'plab mustaqil GURUHLARGA xizmat qiladi - har birining
o'z darslar jadvali va o'z havolasi bor.
"""
import secrets
import sqlite3
from contextlib import contextmanager

DB_PATH = "bot_data.db"


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
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id INTEGER,
                group_id INTEGER,
                username TEXT,
                first_name TEXT,
                active INTEGER DEFAULT 1,
                subscribed_at TEXT DEFAULT (datetime('now')),
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
                created_at TEXT DEFAULT (datetime('now'))
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
        row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        return row


def get_group_by_code(code: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE invite_code = ?", (code,)).fetchone()


def get_group_by_id(group_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()


def get_groups_owned_by(owner_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM groups WHERE owner_id = ? ORDER BY created_at", (owner_id,)
        ).fetchall()


def get_all_groups():
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups ORDER BY created_at").fetchall()


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
    """Foydalanuvchi obuna bo'lgan (faol) guruhlar ro'yxati."""
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


def get_upcoming_lessons(group_id, limit=50):
    with get_db() as conn:
        return conn.execute("""
            SELECT * FROM lessons
            WHERE group_id = ? AND datetime(start_time) >= datetime('now')
            ORDER BY start_time ASC
            LIMIT ?
        """, (group_id, limit)).fetchall()


def get_all_future_lessons():
    """Barcha guruhlardagi hali o'tmagan darslar - eslatma tekshiruvchisi uchun."""
    with get_db() as conn:
        return conn.execute("""
            SELECT * FROM lessons
            WHERE datetime(start_time) >= datetime('now', '-1 day')
            ORDER BY start_time ASC
        """).fetchall()


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
