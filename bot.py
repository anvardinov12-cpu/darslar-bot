"""
Darslar uchun eslatma yuboruvchi Telegram bot.

Ishlash tartibi:
  - Har kim /start bossa - obunachi bo'lib qoladi
  - Admin /add_lessons buyrug'idan keyin darslar ro'yxatini (matn ko'rinishida) yuboradi
    - bir vaqtning o'zida 20+ ta darsni qo'shish mumkin
  - Bot har daqiqada tekshiradi va har bir darsdan 1 kun, 12 soat, 6 soat, 1 soat oldin
    hamda dars boshlanganda BARCHA faol obunachilarga xabar yuboradi

Ishga tushirish:
  1) .env faylida BOT_TOKEN va ADMIN_IDS ni to'ldiring (README.md ga qarang)
  2) pip install -r requirements.txt
  3) python bot.py
"""
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database as db
from parser import parse_lessons_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

# Eslatma turlari: (kod, dars boshlanishidan qancha oldin, ko'rsatiladigan matn)
REMINDER_TYPES = [
    ("1d", timedelta(days=1), "1 kun"),
    ("12h", timedelta(hours=12), "12 soat"),
    ("6h", timedelta(hours=6), "6 soat"),
    ("1h", timedelta(hours=1), "1 soat"),
    ("start", timedelta(minutes=0), None),  # None -> "hozir boshlanmoqda" xabari
]

CHECK_INTERVAL_SECONDS = 60


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------------------- Foydalanuvchi buyruqlari ----------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_subscriber(user.id, user.username, user.first_name)
    await update.message.reply_text(
        "Assalomu alaykum! ✅ Siz darslar eslatmalariga obuna bo'ldingiz.\n\n"
        "Har bir darsdan *1 kun*, *12 soat*, *6 soat*, *1 soat* oldin va "
        "dars *boshlanganda* sizga avtomatik xabar boraveradi.\n\n"
        "Buyruqlar:\n"
        "/lessons - yaqin darslar ro'yxati\n"
        "/stop - obunani bekor qilish",
        parse_mode=ParseMode.MARKDOWN,
    )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.remove_subscriber(update.effective_user.id)
    await update.message.reply_text(
        "Obuna bekor qilindi. Istalgan vaqt /start bosib qayta obuna bo'lishingiz mumkin."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*Buyruqlar:*\n"
        "/start - obuna bo'lish\n"
        "/stop - obunani bekor qilish\n"
        "/lessons - yaqin darslar ro'yxati\n"
    )
    if is_admin(update.effective_user.id):
        text += (
            "\n*Admin buyruqlari:*\n"
            "/add\\_lessons - darslar ro'yxatini qo'shish (pastga qarang)\n"
            "/delete\\_lesson <id> - darsni o'chirish\n"
            "/stats - statistika\n\n"
            "`/add_lessons` buyrug'ini yozib, keyingi qatorlarga darslarni shu formatda joylashtiring:\n\n"
            "```\n"
            "O'qituvchi ismi\n"
            "Учитель\n"
            "Dars nomi\n"
            "Fan nomi\n"
            "2026-08-03 20:00\n"
            "```\n"
            "Har bir dars xuddi shu 5 qatordan iborat bo'lishi kerak, "
            "va istalgancha darsni ketma-ket joylashtirsangiz bo'ladi (20, 50, farqi yo'q)."
        )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def lessons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_upcoming_lessons(limit=20)
    if not rows:
        await update.message.reply_text("Hozircha rejalashtirilgan darslar yo'q.")
        return

    lines = ["*Yaqin darslar:*\n"]
    for r in rows:
        dt = datetime.strptime(r["start_time"], "%Y-%m-%d %H:%M:%S")
        lines.append(
            f"📅 {dt.strftime('%d.%m %H:%M')} - *{r['title']}*\n"
            f"   👤 {r['teacher']} | {r['subject']}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------- Admin buyruqlari ----------------------

async def add_lessons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return

    # /add_lessons dan keyingi matnni olamiz (buyruqning o'zidan keyingi qatorlar)
    full_text = update.message.text
    # Birinchi qatordagi "/add_lessons" so'zini olib tashlaymiz
    body = full_text.split("\n", 1)
    text_to_parse = body[1] if len(body) > 1 else ""

    if not text_to_parse.strip():
        await update.message.reply_text(
            "Darslar matnini /add_lessons buyrug'i bilan BIRGA, keyingi qatorlarga yozib yuboring.\n"
            "Format uchun /help ga qarang."
        )
        return

    lessons, errors = parse_lessons_text(text_to_parse)

    added = 0
    for lesson in lessons:
        db.add_lesson(
            title=lesson["title"],
            teacher=lesson["teacher"],
            subject=lesson["subject"],
            start_time_iso=lesson["start_time_iso"],
        )
        added += 1

    reply = f"✅ {added} ta dars qo'shildi."
    if errors:
        reply += "\n\n⚠️ Quyidagi qismlarda xatolik topildi va o'tkazib yuborildi:\n" + "\n".join(errors)

    await update.message.reply_text(reply)


async def delete_lesson_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /delete_lesson <id>\n(id ni /lessons orqali topolmaysiz hozircha, /admin_lessons qo'shilishi mumkin)")
        return
    try:
        lesson_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("id raqam bo'lishi kerak.")
        return
    db.delete_lesson(lesson_id)
    await update.message.reply_text(f"Dars #{lesson_id} o'chirildi.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    subs = db.count_subscribers()
    lessons = db.get_upcoming_lessons(limit=1000)
    await update.message.reply_text(
        f"👥 Obunachilar: {subs}\n📚 Yaqin darslar soni: {len(lessons)}"
    )


# ---------------------- Eslatmalarni yuborish ----------------------

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    lessons = db.get_all_future_lessons()
    subscribers = db.get_active_subscribers()

    if not subscribers:
        return

    for lesson in lessons:
        start_time = datetime.strptime(lesson["start_time"], "%Y-%m-%d %H:%M:%S")

        for code, offset, label in REMINDER_TYPES:
            reminder_moment = start_time - offset

            # Vaqti keldimi (o'tgan CHECK_INTERVAL ichida) va hali yuborilmaganmi?
            already_sent = db.was_reminder_sent(lesson["id"], code)
            if already_sent:
                continue

            window_start = reminder_moment
            window_end = reminder_moment + timedelta(seconds=CHECK_INTERVAL_SECONDS)

            if window_start <= now < window_end:
                if code == "start":
                    text = (
                        f"🔴 *Dars boshlanmoqda!*\n\n"
                        f"📚 {lesson['title']}\n"
                        f"👤 {lesson['teacher']}\n"
                        f"🏷 {lesson['subject']}"
                    )
                else:
                    text = (
                        f"⏰ *{label} qoldi*\n\n"
                        f"📚 {lesson['title']}\n"
                        f"👤 {lesson['teacher']}\n"
                        f"🏷 {lesson['subject']}\n"
                        f"🕐 Boshlanish: {start_time.strftime('%d.%m.%Y %H:%M')}"
                    )

                for user_id in subscribers:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        logger.warning(f"Xabar yuborilmadi user_id={user_id}: {e}")

                db.mark_reminder_sent(lesson["id"], code)


# ---------------------- Ishga tushirish ----------------------

def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable topilmadi! .env faylni tekshiring.")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("lessons", lessons_cmd))
    app.add_handler(CommandHandler("add_lessons", add_lessons_cmd))
    app.add_handler(CommandHandler("delete_lesson", delete_lesson_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))

    app.job_queue.run_repeating(check_reminders, interval=CHECK_INTERVAL_SECONDS, first=10)

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
