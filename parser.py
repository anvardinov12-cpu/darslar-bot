"""
Admin yuborgan matnni (darslar ro'yxatini) o'qib, tuzilgan darslarga aylantiradi.

Kutilayotgan format - har bir dars 5 qatordan iborat blok:
    O'qituvchi ismi
    Учитель                (bu qator e'tiborga olinmaydi, faqat belgi)
    Dars nomi
    Fan / kategoriya
    YYYY-MM-DD HH:MM

Bloklar orasida bo'sh qator bo'lishi shart emas - ketma-ket ham bo'lishi mumkin,
chunki har doim aniq 5 qatordan iborat deb hisoblanadi.
"""
import re
from datetime import datetime

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$")


def parse_lessons_text(text: str):
    """
    Matnni parse qiladi va (lessons, errors) qaytaradi.
    lessons: list of dict{teacher, title, subject, start_time_iso}
    errors: list of str - agar formatga mos kelmagan qismlar bo'lsa
    """
    # Bo'sh qatorlarni olib tashlab, faqat mazmunli qatorlarni qoldiramiz
    raw_lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in raw_lines if ln != ""]

    lessons = []
    errors = []

    i = 0
    block_num = 0
    while i < len(lines):
        # Har bir dars bloki: Teacher, "Учитель", Title, Subject, DateTime
        chunk = lines[i:i + 5]
        block_num += 1
        if len(chunk) < 5:
            if chunk:
                errors.append(f"Blok #{block_num}: yetarli qator yo'q ({len(chunk)}/5) - o'tkazib yuborildi")
            break

        teacher, role_marker, title, subject, date_str = chunk

        if not DATE_RE.match(date_str):
            errors.append(
                f"Blok #{block_num}: sana formati noto'g'ri -> '{date_str}' "
                f"(kutilgan: YYYY-MM-DD HH:MM)"
            )
            i += 5
            continue

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            errors.append(f"Blok #{block_num}: sanani o'qib bo'lmadi -> '{date_str}'")
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
