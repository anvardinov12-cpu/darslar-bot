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
                owner_id INTEGER NOT NULL,
                chat_id TEXT,
                secret_token TEXT UNIQUE
            )
        """)
        
        # <--- O'ZGARISH 1: secret_token ustuni bazada yo'q bo'lsa, xatolik bermasdan qo'shish uchun
        try:
            conn.execute("ALTER TABLE groups ADD COLUMN secret_token TEXT")
        except Exception:
            pass
        
        try:
            conn.execute("ALTER TABLE groups ADD COLUMN chat_id TEXT")
        except Exception:
            pass
        
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
                rem_3h INTEGER DEFAULT 1,
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
    secret_token = secrets.token_hex(6) # <--- Yangi guruh uchun 12 xonali maxfiy kalit yaratamiz
    
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO groups (name, invite_code, owner_id, secret_token) VALUES (?, ?, ?, ?)", # <--- secret_token qo'shildi
            (name, code, owner_id, secret_token) # <--- secret_token qiymati berildi
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

def get_group_by_secret_token(token: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE secret_token = ?", (token,)).fetchone()
        
def get_group_by_code(code: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM groups WHERE invite_code = ?", (code,)).fetchone()

def delete_group(group_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.execute("DELETE FROM subscribers WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM lessons WHERE group_id = ?", (group_id,))

def link_telegram_group(group_id: int, chat_id: str):
    with get_db() as conn:
        conn.execute("UPDATE groups SET chat_id = ? WHERE id = ?", (chat_id, group_id))
        
def unlink_telegram_group(group_id: int):
    with get_db() as conn:
        conn.execute("UPDATE groups SET chat_id = NULL WHERE id = ?", (group_id,))
        
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

# --- Obunani bekor qilish uchun funksiya ---
def remove_subscriber(user_id: int, group_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM subscribers WHERE user_id = ? AND group_id = ?", (user_id, group_id))
        
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
    
    # Agar foydalanuvchi bazada umuman yo'q bo'lsa, avval uni yaratib olamiz
    if not curr:
        with get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        curr = get_user_settings(user_id)
        
    current_val = curr.get(col, 1) if curr else 1
    new_val = 0 if current_val == 1 else 1
    
    with get_db() as conn:
        conn.execute(f"UPDATE user_settings SET {col} = ? WHERE user_id = ?", (new_val, user_id))
        conn.commit()
        
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

def get_all_groups_with_owners():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT g.id, g.name, g.invite_code, g.owner_id,
                   COALESCE(u.full_name, 'Foydalanuvchi') as owner_name
            FROM groups g
            LEFT JOIN users u ON g.owner_id = u.user_id
            ORDER BY g.id DESC
        """).fetchall()
        return [dict(r) for r in rows]

def get_all_lessons_with_groups():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT l.id, l.title, l.teacher, l.start_time, g.name as group_name
            FROM lessons l
            JOIN groups g ON l.group_id = g.id
            ORDER BY l.start_time ASC
        """).fetchall()
        return [dict(r) for r in rows]

def get_all_users_list():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT s.user_id, 
                   CASE 
                       WHEN u.full_name IS NULL OR TRIM(u.full_name) = '' THEN 'Foydalanuvchi'
                       ELSE u.full_name 
                   END as full_name 
            FROM subscribers s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.user_id != 0
            ORDER BY s.user_id ASC
        """).fetchall()
        return [dict(r) for r in rows]

# --- Ban / Kick User ---
def delete_user_from_bot(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM sent_reminders WHERE user_id = ?", (user_id,))

# --- Avtomatik Tozalash (Cleanup Database) ---
def cleanup_expired_data():
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        # 1. Muddati o'tib ketgan darslarni o'chirish (start_time hozirgi vaqtdan o'tib ketgan bo'lsa)
        conn.execute("DELETE FROM lessons WHERE start_time < ?", (now_str,))
        
        # 2. Asl guruhi bazadan o'chib ketgan, lekin subscribers jadvalida qolib ketgan "yetim" obunalarni tozalash
        conn.execute("""
            DELETE FROM subscribers 
            WHERE group_id != 0 AND group_id NOT IN (SELECT id FROM groups)
        """)
        
        # 3. Allaqachon o'chib ketgan darslarga tegishli eskirgan sent_reminders loglarini tozalash
        conn.execute("""
            DELETE FROM sent_reminders 
            WHERE lesson_id NOT IN (SELECT id FROM lessons)
        """)

# --- DATABASE.PY ga qo'shiladigan qism ---

# 1. init_db() funksiyasi ichiga quyidagi jadvallarni qo'shing:
def init_db():
    with get_db() as conn:
        # ... (sizdagi mavjud jadvallar shu yerda qoladi) ...
        
        # YANGI: Fanlar va haftalik jadval jadvallari
        conn.execute("""
            CREATE TABLE IF NOT EXISTS group_curriculum (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                subject_title TEXT NOT NULL,
                total_count INTEGER NOT NULL,
                current_index INTEGER DEFAULT 1,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_day_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                day_index INTEGER NOT NULL, -- 0: Dushanba, 1: Seshanba, ..., 5: Shanba
                schedule_text TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)

# 2. Faylning oxiriga quyidagi funksiyalarni qo'shib qo'ying:
def get_day_schedule(group_id: int, day_index: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT schedule_text FROM weekly_day_schedule WHERE group_id = ? AND day_index = ?",
            (group_id, day_index)
        ).fetchone()
        
        if not row or not row["schedule_text"]:
            return ""
            
        text = row["schedule_text"]
        
        # Umumiy ro'yxatdagi mavjud fanlarni olamiz
        curriculum_items = get_all_curriculum(group_id)
        valid_titles = {item["subject_title"].strip().lower() for item in curriculum_items}
        
        # Agar umumiy ro'yxat bo'sh bo'lsa, matnni o'zini qaytaramiz yoki bo'shatamiz
        if not valid_titles:
            return text
            
        lines = text.split("\n")
        filtered_lines = []
        counter = 1
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(".", 1)
            subj_name = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            
            # Agar fan umumiy ro'yxatda mavjud bo'lsagina qoldiramiz
            if subj_name.lower() in valid_titles:
                filtered_lines.append(f"{counter}. {subj_name}")
                counter += 1
                
        return "\n".join(filtered_lines)

def save_day_schedule(group_id: int, day_index: int, text: str):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM weekly_day_schedule WHERE group_id = ? AND day_index = ?",
            (group_id, day_index)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE weekly_day_schedule SET schedule_text = ? WHERE group_id = ? AND day_index = ?",
                (text, group_id, day_index)
            )
        else:
            conn.execute(
                "INSERT INTO weekly_day_schedule (group_id, day_index, schedule_text) VALUES (?, ?, ?)",
                (group_id, day_index, text)
            )

def get_all_curriculum(group_id: int):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM group_curriculum WHERE group_id = ?", (group_id,)).fetchall()
        return [dict(r) for r in rows]

def add_curriculum_item(group_id: int, title: str, total: int):
    with get_db() as conn:
        # Boshlang'ich qolgan darslar soni jami dars soniga teng bo'ladi
        conn.execute(
            "INSERT INTO group_curriculum (group_id, subject_title, total_count, current_index) VALUES (?, ?, ?, ?)",
            (group_id, title, total, total)
        )

def delete_curriculum_item(item_id: int):
    with get_db() as conn:
        # 1. O'chirilayotgan fanning ma'lumotlarini olib olamiz
        item = conn.execute("SELECT group_id, subject_title FROM group_curriculum WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return
        
        group_id = item["group_id"]
        subject_title = item["subject_title"].strip().lower()

        # 2. Fanni bazadagi umumiy ro'yxatdan o'chiramiz
        conn.execute("DELETE FROM group_curriculum WHERE id = ?", (item_id,))

        # 3. Shu guruhning hafta kunlari jadvallaridan ham bu fanni tozalab chiqamiz
        schedules = conn.execute("SELECT id, schedule_text FROM weekly_day_schedule WHERE group_id = ?", (group_id,)).fetchall()
        
        for sch in schedules:
            sch_id = sch["id"]
            text = sch["schedule_text"]
            if not text:
                continue
            
            lines = text.split("\n")
            new_lines = []
            counter = 1
            changed = False
            
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                
                # Qatordagi fan nomini ajratib olamiz (masalan: "1. Matematika" -> "Matematika")
                parts = line_str.split(".", 1)
                curr_name = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                
                # Agar o'chirilayotgan fanga mos kelsa, uni tashlab yuboramiz
                if curr_name.lower() == subject_title:
                    changed = True
                    continue
                
                # Qolgan fanlarni tartib raqamini yangilab yig'amiz
                new_lines.append(f"{counter}. {curr_name}")
                counter += 1
            
            # Agar ro'yxatdan fan o'chirilgan bo'lsa, bazadagi jadvalni yangilaymiz
            if changed:
                new_text = "\n".join(new_lines)
                conn.execute("UPDATE weekly_day_schedule SET schedule_text = ? WHERE id = ?", (new_text, sch_id))

def update_curriculum_index(item_id: int, new_index: int):
    with get_db() as conn:
        conn.execute("UPDATE group_curriculum SET current_index = ? WHERE id = ?", (new_index, item_id))
