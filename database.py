import os
import sqlite3
import secrets
from contextlib import contextmanager
from datetime import datetime
import pytz

# Railway Volume papkasi mavjud bo'lsa, shu yerga, aks holda joriy papkaga saqlaydi
DB_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_PATH = os.path.join(DB_DIR, "modern_bot.db")

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

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT
            )
        """)
        # Bazada oldindan bor bo'lgan foydalanuvchilarni ham xatolik bermasligi uchun qo'shib qo'yamiz
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, full_name)
            SELECT DISTINCT user_id, 'Foydalanuvchi' FROM subscribers WHERE user_id != 0
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                rem_24h INTEGER DEFAULT 1,
                rem_12h INTEGER DEFAULT 1,
                rem_6h INTEGER DEFAULT 1,
                rem_1h INTEGER DEFAULT 1,
                rem_15m INTEGER DEFAULT 1,
                rem_now INTEGER DEFAULT 1
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
                user_id INTEGER,
                reminder_type TEXT,
                PRIMARY KEY (lesson_id, user_id, reminder_type)
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

# --- Subscribers & Users ---
def add_subscriber(user_id: int, group_id: int, full_name: str = ""):
    with get_db() as conn:
        if group_id != 0:
            conn.execute("INSERT OR IGNORE INTO subscribers (user_id, group_id) VALUES (?, ?)", (user_id, group_id))
        conn.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        if full_name:
            conn.execute("""
                INSERT INTO users (user_id, full_name) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET full_name = ?
            """, (user_id, full_name, full_name))

def get_subscribers(group_id: int):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT s.user_id, COALESCE(u.full_name, 'Foydalanuvchi') as full_name 
            FROM subscribers s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.group_id = ?
        """, (group_id,)).fetchall()
        return [dict(r) for r in rows]

# --- User Notification Settings ---
def get_user_settings(user_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
            row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row)

def toggle_user_setting(user_id: int, r_type: str):
    col = f"rem_{r_type}"
    curr = get_user_settings(user_id)
    new_val = 0 if curr.get(col, 1) == 1 else 1
    with get_db() as conn:
        conn.execute(f"UPDATE user_settings SET {col} = ? WHERE user_id = ?", (new_val, user_id))
    return new_val

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

# --- Reminders Log ---
def was_reminder_sent(lesson_id: int, user_id: int, r_type: str):
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM sent_reminders WHERE lesson_id = ? AND user_id = ? AND reminder_type = ?", (lesson_id, user_id, r_type)).fetchone()
        return row is not None

def mark_reminder_sent(lesson_id: int, user_id: int, r_type: str):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO sent_reminders (lesson_id, user_id, reminder_type) VALUES (?, ?, ?)", (lesson_id, user_id, r_type))

# --- Super Admin Stats ---
def get_total_stats():
    with get_db() as conn:
        total_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM subscribers").fetchone()[0]
        total_groups = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        total_lessons = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
        return total_users, total_groups, total_lessons

def get_all_users_list():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT s.user_id, COALESCE(u.full_name, 'Foydalanuvchi') as full_name 
            FROM subscribers s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.user_id != 0
        """).fetchall()
        return [dict(r) for r in rows]

# --- Ban / Kick User ---
def delete_user_from_bot(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM sent_reminders WHERE user_id = ?", (user_id,))
