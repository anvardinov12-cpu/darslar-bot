"""
Darslar ro'yxatini to'g'ri parse qilish moduli.
"""
import re
from datetime import datetime

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$")

def parse_lessons_text(text: str):
    raw_lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in raw_lines if ln != ""]

    lessons = []
    errors = []

    i = 0
    block_num = 0
    while i < len(lines):
        chunk = lines[i:i + 5]
        block_num += 1
        if len(chunk) < 5:
            if chunk:
                errors.append(f"Blok #{block_num}: qatorlar yetarli emas ({len(chunk)}/5) - o'tkazib yuborildi")
            break

        teacher, role_marker, title, subject, date_str = chunk

        if not DATE_RE.match(date_str):
            errors.append(
                f"Blok #{block_num}: sana formati noto'g'ri -> '{date_str}' (kutilgan format: YYYY-MM-DD HH:MM)"
            )
            i += 5
            continue

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            errors.append(f"Blok #{block_num}: sana ma'lumoti xato -> '{date_str}'")
            i += 5
            continue

        lessons.append({
            "teacher": teacher,
            "title": title,
            "subject": subject,
            "start_time_iso": dt.strftime("%Y-%m-%d %H:%M:00"),
        })
        i += 5

    return lessons, errors
