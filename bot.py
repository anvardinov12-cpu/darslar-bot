"""
Darslar uchun eslatma yuboruvchi Telegram bot - KO'P GURUHLI versiya.

Ishlash tartibi:
  - Istalgan kishi /create_group <Guruh nomi> orqali o'ziga xos guruh (jadval) yaratadi
    va o'sha guruhga xos HAVOLA oladi
  - Havolani odamlarga tarqatadi - kimdir shu havolani bossa, botga /start bilan
    kiradi va AVTOMATIK o'sha guruhga obuna bo'ladi (hech narsa tanlash shart emas)
  - Guruh yaratgan kishi (owner) /add_lessons orqali o'z guruhiga darslar qo'shadi
  - Har bir dars uchun 1 kun, 12 soat, 6 soat, 1 soat oldin va boshlanganda
    FAQAT O'SHA GURUH obunachilariga xabar boradi - boshqa guruhlarga tegmaydi

Bitta bot - cheksiz mustaqil guruh. Yangi bot yaratish shart emas.
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
)

import database as db
from parser import parse_lessons_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SUPER_ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

REMINDER_TYPES = [
    ("1d", timedelta(days=1), "1 kun"),
    ("12h", timedelta(hours=12), "12 soat"),
    ("6h", timedelta(hours=6), "6 soat"),
    ("1h", timedelta(hours=1), "1 soat"),
    ("start", timedelta(minutes=0), None),
]

CHECK_INTERVAL_SECONDS = 60


def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS


def can_manage_group(user_id: int, group) -> bool:
    """Guruh egasi yoki bosh admin shu guruhni boshqara oladi."""
    if group is None:
        return False
    return group["owner_id"] == user_id or is_super_admin(user_id)


# ---------------------- Guruh yaratish va obuna (deep link) ----------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if not group:
            await update.message.reply_text(
                "❌ Bu havola noto'g'ri yoki muddati o'tgan. Guruh egasidan yangi havola so'rang."
            )
            return
        db.add_subscriber(user.id, group["id"], user.username, user.first_name)
        await update.message.reply_text(
            f"✅ Siz *{group['name']}* guruhiga obuna bo'ldingiz!\n\n"
            f"Har bir darsdan *1 kun*, *12 soat*, *6 soat*, *1 soat* oldin va "
            f"dars *boshlanganda* sizga avtomatik xabar boradi.\n\n"
            f"/lessons - shu guruhning yaqin darslarini ko'rish\n"
            f"/stop - obunani bekor qilish",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Havolasiz oddiy /start - foydalanuvchining hozirgi guruhlarini ko'rsatamiz
    groups = db.get_user_groups(user.id)
    if groups:
        names = "\n".join(f"• {g['name']}" for g in groups)
        text = (
            "Assalomu alaykum! Siz quyidagi guruhlarga obunasiz:\n\n"
            f"{names}\n\n"
            "/lessons - yaqin darslarni ko'rish\n"
            "/create_group <nom> - o'z guruhingizni yaratish"
        )
    else:
        text = (
            "Assalomu alaykum! 👋\n\n"
            "Bu bot orqali darslar jadvaliga obuna bo'lib, eslatmalar olishingiz mumkin.\n\n"
            "• Agar sizga guruh havolasi yuborishgan bo'lsa - o'sha havolani bosing,\n"
            "  avtomatik obuna bo'lasiz.\n"
            "• Agar o'zingiz yangi guruh (jadval) yaratmoqchi bo'lsangiz:\n"
            "  /create_group Guruh nomi"
        )
    await update.message.reply_text(text)


async def create_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text(
            "Foydalanish: /create_group Guruh nomi\n"
            "Masalan: /create_group Tazkiya kursi - 1-guruh"
        )
        return

    group = db.create_group(name, user.id)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=g_{group['invite_code']}"

    await update.message.reply_text(
        f"✅ Guruh yaratildi: *{group['name']}*\n\n"
        f"Quyidagi havolani odamlarga yuboring - havolani bosgan kishi "
        f"avtomatik shu guruhga obuna bo'ladi:\n\n"
        f"`{link}`\n\n"
        f"Darslarni qo'shish uchun: /add_lessons {group['id']}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def my_groups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    owned = db.get_groups_owned_by(user.id)
    if not owned:
        await update.message.reply_text(
            "Sizga tegishli guruh yo'q. Yaratish uchun: /create_group Guruh nomi"
        )
        return

    me = await context.bot.get_me()
    lines = ["*Sizning guruhlaringiz:*\n"]
    for g in owned:
        link = f"https://t.me/{me.username}?start=g_{g['invite_code']}"
        subs = db.count_subscribers(g["id"])
        lines.append(
            f"📚 *{g['name']}* (id: {g['id']})\n"
            f"   👥 {subs} obunachi\n"
            f"   🔗 `{link}`"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_groups(user.id)
    if not groups:
        await update.message.reply_text("Siz hech qanday guruhga obuna emassiz.")
        return
    if not context.args:
        lines = ["Qaysi guruhdan chiqmoqchisiz? Guruh id raqamini yozing:\n"]
        for g in groups:
            lines.append(f"• {g['name']} - /stop {g['id']}")
        await update.message.reply_text("\n".join(lines))
        return
    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Guruh id raqam bo'lishi kerak.")
        return
    db.remove_subscriber(user.id, group_id)
    await update.message.reply_text("Obuna bekor qilindi.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*Buyruqlar:*\n"
        "/create_group <nom> - yangi guruh (jadval) yaratish va havola olish\n"
        "/my_groups - sizga tegishli guruhlar va ularning havolalari\n"
        "/add_lessons <guruh_id> - guruhga darslar qo'shish (pastga qarang)\n"
        "/lessons - obuna bo'lgan guruhlaringizning yaqin darslari\n"
        "/stop <guruh_id> - biror guruhdan obunani bekor qilish\n\n"
        "*Darslarni qo'shish formati:*\n"
        "`/add_lessons 3` deb yozing (3 - guruh id), keyingi qatorlarga:\n\n"
        "```\n"
        "O'qituvchi ismi\n"
        "Учитель\n"
        "Dars nomi\n"
        "Fan nomi\n"
        "2026-08-03 20:00\n"
        "```\n"
        "Har bir dars aynan shu 5 qatordan iborat, istalgancha darsni ketma-ket "
        "joylashtirishingiz mumkin (20, 50, farqi yo'q)."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def lessons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_groups(user.id)
    if not groups:
        await update.message.reply_text("Siz hali hech qanday guruhga obuna emassiz.")
        return

    all_lines = []
    for g in groups:
        rows = db.get_upcoming_lessons(g["id"], limit=20)
        if not rows:
            continue
        all_lines.append(f"*{g['name']}*")
        for r in rows:
            dt = datetime.strptime(r["start_time"], "%Y-%m-%d %H:%M:%S")
            all_lines.append(
                f"📅 {dt.strftime('%d.%m %H:%M')} - {r['title']}\n"
                f"   👤 {r['teacher']} | {r['subject']}"
            )
        all_lines.append("")

    if not all_lines:
        await update.message.reply_text("Hozircha rejalashtirilgan darslar yo'q.")
        return

    await update.message.reply_text("\n\n".join(all_lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------- Admin: darslarni boshqarish ----------------------

async def add_lessons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "Foydalanish: /add_lessons <guruh_id>, keyingi qatorlarga darslarni yozing.\n"
            "Guruh id ni /my_groups orqali topasiz."
        )
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Guruh id raqam bo'lishi kerak. Masalan: /add_lessons 3")
        return

    group = db.get_group_by_id(group_id)
    if not can_manage_group(user.id, group):
        await update.message.reply_text("Bu guruhni boshqarish huquqingiz yo'q.")
        return

    full_text = update.message.text
    parts = full_text.split("\n", 1)
    text_to_parse = parts[1] if len(parts) > 1 else ""

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
            group_id=group_id,
            title=lesson["title"],
            teacher=lesson["teacher"],
            subject=lesson["subject"],
            start_time_iso=lesson["start_time_iso"],
        )
        added += 1

    reply = f"✅ *{group['name']}* guruhiga {added} ta dars qo'shildi."
    if errors:
        reply += "\n\n⚠️ Quyidagi qismlarda xatolik topildi va o'tkazib yuborildi:\n" + "\n".join(errors)

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def delete_lesson_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Foydalanish: /delete_lesson <dars_id>")
        return
    try:
        lesson_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("id raqam bo'lishi kerak.")
        return

    lesson = db.get_lesson(lesson_id)
    if not lesson:
        await update.message.reply_text("Bunday dars topilmadi.")
        return

    group = db.get_group_by_id(lesson["group_id"])
    if not can_manage_group(user.id, group):
        await update.message.reply_text("Bu darsni o'chirish huquqingiz yo'q.")
        return

    db.delete_lesson(lesson_id)
    await update.message.reply_text(f"Dars #{lesson_id} o'chirildi.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat bosh admin uchun.")
        return
    groups = db.get_all_groups()
    lines = [f"📊 Jami guruhlar: {len(groups)}\n"]
    for g in groups:
        subs = db.count_subscribers(g["id"])
        lines.append(f"• {g['name']} (id {g['id']}) - {subs} obunachi")
    await update.message.reply_text("\n".join(lines))


# ---------------------- Eslatmalarni yuborish ----------------------

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    lessons = db.get_all_future_lessons()

    for lesson in lessons:
        start_time = datetime.strptime(lesson["start_time"], "%Y-%m-%d %H:%M:%S")

        for code, offset, label in REMINDER_TYPES:
            if db.was_reminder_sent(lesson["id"], code):
                continue

            reminder_moment = start_time - offset
            window_start = reminder_moment
            window_end = reminder_moment + timedelta(seconds=CHECK_INTERVAL_SECONDS)

            if window_start <= now < window_end:
                subscribers = db.get_active_subscribers(lesson["group_id"])
                if not subscribers:
                    db.mark_reminder_sent(lesson["id"], code)
                    continue

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

async def post_init(application: Application):
    """Bot ishga tushganda Telegram'ning '/' buyruqlar menyusini (tugmalar) sozlaydi."""
    await application.bot.set_my_commands([
        ("start", "Botni ishga tushirish / obuna bo'lish"),
        ("lessons", "Yaqin darslarni ko'rish"),
        ("create_group", "Yangi guruh (jadval) yaratish"),
        ("my_groups", "Guruhlarim va havolalarim"),
        ("add_lessons", "Guruhga darslar qo'shish"),
        ("stop", "Obunani bekor qilish"),
        ("help", "Yordam"),
    ])


def main():
    if not BOT_TOKEN:
        env_keys = sorted(os.environ.keys())
        logger.error("BOT_TOKEN topilmadi! Mavjud environment variable nomlari:")
        for k in env_keys:
            logger.error(f"  - {k}")
        raise SystemExit("BOT_TOKEN environment variable topilmadi! Yuqoridagi ro'yxatni tekshiring.")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("lessons", lessons_cmd))
    app.add_handler(CommandHandler("create_group", create_group_cmd))
    app.add_handler(CommandHandler("my_groups", my_groups_cmd))
    app.add_handler(CommandHandler("add_lessons", add_lessons_cmd))
    app.add_handler(CommandHandler("delete_lesson", delete_lesson_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))

    app.job_queue.run_repeating(check_reminders, interval=CHECK_INTERVAL_SECONDS, first=10)

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
