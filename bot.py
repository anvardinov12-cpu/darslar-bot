import logging
import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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
SUPER_ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

TZ = pytz.timezone("Asia/Tashkent")

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
    if group is None:
        return False
    return group["owner_id"] == user_id or is_super_admin(user_id)

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📚 Yaqin darslar (/lessons)"), KeyboardButton("➕ Yangi guruh (/create_group)")],
        [KeyboardButton("📂 Guruhlarim (/my_groups)"), KeyboardButton("❓ Yordam (/help)")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------------------- Commands ----------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if not group:
            await update.message.reply_text("❌ Bu havola noto'g'ri yoki guruh o'chirilgan.")
            return
        db.add_subscriber(user.id, group["id"], user.username, user.first_name)
        await update.message.reply_text(
            f"✅ Siz *{group['name']}* guruhiga muvaffaqiyatli obuna bo'ldingiz!\n\n"
            f"Darslar vaqtidan oldin va dars boshlanganda avtomatik bildirishnoma olasiz.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return

    text = (
        f"Assalomu alaykum, {user.first_name}! 👋\n\n"
        f"Ushbu bot darslar va mashg'ulotlar haqida o'z vaqtida eslatib turadi.\n"
        f"Pastdagi tugmalar orqali botdan foydalanishingiz mumkin."
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def create_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = " ".join(context.args).strip()
    
    if not name:
        await update.message.reply_text(
            "⚠️ Guruh nomini yozing!\n\n"
            "Masalan:\n`/create_group Tazkiya kursi - 1-guruh`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    group = db.create_group(name, user.id)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=g_{group['invite_code']}"

    text = (
        f"✅ *Guruh yaratildi!*\n\n"
        f"📌 *Guruh Nomi:* {group['name']}\n"
        f"🆔 *Guruh ID:* `{group['id']}`\n\n"
        f"🔗 *Taklif havolasi (Odamlarga ulashish uchun):*\n`{link}`\n\n"
        f"➕ Dars qo'shish uchun quyidagi buyruqni bosing:\n`/add_lessons {group['id']}`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def my_groups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    owned = db.get_groups_owned_by(user.id)
    
    if not owned:
        await update.message.reply_text(
            "Siz yaratgan guruhlar yo'q.\n"
            "Yangi guruh yaratish uchun: `/create_group Guruh Nomi`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    me = await context.bot.get_me()
    lines = ["📋 *Siz egalik qiladigan guruhlar:*\n"]
    for g in owned:
        link = f"https://t.me/{me.username}?start=g_{g['invite_code']}"
        subs = db.count_subscribers(g["id"])
        lines.append(
            f"📚 *{g['name']}* (ID: `{g['id']}`)\n"
            f"👥 Obunachilar: {subs} ta\n"
            f"🔗 Havola: `{link}`\n"
            f"🛠 *Boshqarish:*\n"
            f"  └ Dars qo'shish: `/add_lessons {g['id']}`\n"
            f"  └ Nomini o'zgartirish: `/edit_group {g['id']} Yangi Nom`\n"
            f"  └ Guruhni o'chirish: `/delete_group {g['id']}`\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def edit_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("Foydalanish: `/edit_group <guruh_id> <yangi_nom>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Guruh ID raqam bo'lishi kerak.")
        return

    new_name = " ".join(context.args[1:]).strip()
    group = db.get_group_by_id(group_id)

    if not can_manage_group(user.id, group):
        await update.message.reply_text("❌ Siz bu guruhni o'zgartira olmaysiz!")
        return

    db.update_group_name(group_id, new_name)
    await update.message.reply_text(f"✅ Guruh nomi *{new_name}* deb o'zgartirildi.", parse_mode=ParseMode.MARKDOWN)

async def delete_group_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Foydalanish: `/delete_group <guruh_id>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Guruh ID raqam bo'lishi kerak.")
        return

    group = db.get_group_by_id(group_id)
    if not can_manage_group(user.id, group):
        await update.message.reply_text("❌ Siz bu guruhni o'chira olmaysiz!")
        return

    db.delete_group(group_id)
    await update.message.reply_text(f"🗑 Guruh (ID: {group_id}) va uning darslari o'chirildi.")

async def add_lessons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.args:
        text = (
            "⚠️ *Dars qo'shish yo'riqnomasi:*\n\n"
            "Buyruq va matnni quyidagi shaklda birga yuboring:\n\n"
            "`/add_lessons <guruh_id>`\n"
            "O'qituvchi Ismi\n"
            "Учитель\n"
            "Dars Mavzusi\n"
            "Fan Nomi\n"
            "YYYY-MM-DD HH:MM\n\n"
            "📌 *Misol:*\n"
            "`/add_lessons 1`\n"
            "Anvar Ahmad\n"
            "Учитель\n"
            "Tazkiya - Qalb kasalliklari\n"
            "Aqida\n"
            "2026-08-10 20:00"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Guruh ID raqam bo'lishi kerak. Masalan: /add_lessons 1")
        return

    group = db.get_group_by_id(group_id)
    if not can_manage_group(user.id, group):
        await update.message.reply_text("❌ Siz faqat o'zingiz yaratgan guruhga dars qo'sha olasiz!")
        return

    full_text = update.message.text
    parts = full_text.split("\n", 1)
    text_to_parse = parts[1] if len(parts) > 1 else ""

    if not text_to_parse.strip():
        await update.message.reply_text(
            "⚠️ Dars ma'lumotlarini buyruqdan keyingi qatorlarga yozing!\n"
            "Namuna ko'rish uchun shunchaki `/add_lessons` deb yuboring.",
            parse_mode=ParseMode.MARKDOWN
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

    reply = f"✅ *{group['name']}* guruhiga {added} ta dars muvaffaqiyatli qo'shildi."
    if errors:
        reply += "\n\n⚠️ *Xatoliklar:* \n" + "\n".join(errors)

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

async def delete_lesson_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Foydalanish: `/delete_lesson <dars_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        lesson_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Dars ID raqam bo'lishi kerak.")
        return

    lesson = db.get_lesson(lesson_id)
    if not lesson:
        await update.message.reply_text("Bunday dars topilmadi.")
        return

    group = db.get_group_by_id(lesson["group_id"])
    if not can_manage_group(user.id, group):
        await update.message.reply_text("❌ Siz bu darsni o'chira olmaysiz!")
        return

    db.delete_lesson(lesson_id)
    await update.message.reply_text(f"🗑 Dars (ID: {lesson_id}) o'chirildi.")

async def lessons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_groups(user.id)
    if not groups:
        await update.message.reply_text("Siz hech qaysi guruhga obuna emassiz.")
        return

    all_lines = []
    for g in groups:
        rows = db.get_upcoming_lessons(g["id"], limit=10)
        if not rows:
            continue
        all_lines.append(f"📚 *{g['name']}*")
        for r in rows:
            dt = datetime.strptime(r["start_time"], "%Y-%m-%d %H:%M:%S")
            all_lines.append(
                f" 🆔 Dars ID: `{r['id']}`\n"
                f" 📅 Vaqti: {dt.strftime('%d.%m.%Y %H:%M')}\n"
                f" 📖 Dars: {r['title']}\n"
                f" 👤 Ustoz: {r['teacher']} ({r['subject']})\n"
            )

    if not all_lines:
        await update.message.reply_text("Hozircha rejalashtirilgan darslar yo'q.")
        return

    await update.message.reply_text("\n".join(all_lines), parse_mode=ParseMode.MARKDOWN)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_groups(user.id)
    if not groups:
        await update.message.reply_text("Siz hech qanday guruhga obuna emassiz.")
        return
    if not context.args:
        lines = ["Chiqmoqchi bo'lgan guruh buyrug'ini bosing:\n"]
        for g in groups:
            lines.append(f"• {g['name']} -> `/stop {g['id']}`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        return
    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Guruh ID raqam bo'lishi kerak.")
        return
    db.remove_subscriber(user.id, group_id)
    await update.message.reply_text("✅ Obuna bekor qilindi.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 *Bot buyruqlari:* \n\n"
        "• `/start` - Botni ishga tushirish\n"
        "• `/lessons` - Yaqin darslar ro'yxati\n"
        "• `/create_group <nomi>` - Yangi guruh yaratish\n"
        "• `/my_groups` - Siz yaratgan guruhlar va boshqaruv\n"
        "• `/add_lessons` - Dars qo'shish yo'riqnomasi\n"
        "• `/delete_lesson <dars_id>` - Darsni o'chirish\n"
        "• `/delete_group <guruh_id>` - Guruhni o'chirish\n"
        "• `/stop <guruh_id>` - Guruh obunasini bekor qilish"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if "Yaqin darslar" in msg:
        await lessons_cmd(update, context)
    elif "Yangi guruh" in msg:
        await update.message.reply_text("Yangi guruh yaratish uchun: `/create_group Guruh Nomi`", parse_mode=ParseMode.MARKDOWN)
    elif "Guruhlarim" in msg:
        await my_groups_cmd(update, context)
    elif "Yordam" in msg:
        await help_cmd(update, context)

# ---------------------- Eslatmalar ----------------------

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = db.get_now()
    lessons = db.get_all_future_lessons()

    for lesson in lessons:
        start_time_naive = datetime.strptime(lesson["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = TZ.localize(start_time_naive)

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
                        f"🔴 *Dars boshlandi!*\n\n"
                        f"📚 *Dars:* {lesson['title']}\n"
                        f"👤 *Ustoz:* {lesson['teacher']}\n"
                        f"🏷 *Fan:* {lesson['subject']}"
                    )
                else:
                    text = (
                        f"⏰ *Darsga {label} qoldi!*\n\n"
                        f"📚 *Dars:* {lesson['title']}\n"
                        f"👤 *Ustoz:* {lesson['teacher']}\n"
                        f"🏷 *Fan:* {lesson['subject']}\n"
                        f"🕐 *Boshlanish vaqti:* {start_time.strftime('%d.%m.%Y %H:%M')}"
                    )

                for user_id in subscribers:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        logger.warning(f"Xabar yuborilmadi user_id={user_id}: {e}")

                db.mark_reminder_sent(lesson["id"], code)

# ---------------------- Main ----------------------

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "Botni qayta ishga tushirish"),
        ("lessons", "Yaqin darslar ro'yxati"),
        ("create_group", "Yangi guruh yaratish"),
        ("my_groups", "Guruhlarim va ularni boshqarish"),
        ("add_lessons", "Darslar qo'shish yo'riqnomasi"),
        ("stop", "Obunani bekor qilish"),
        ("help", "Yordam va yo'riqnoma"),
    ])

def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable topilmadi!")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("create_group", create_group_cmd))
    app.add_handler(CommandHandler("edit_group", edit_group_cmd))
    app.add_handler(CommandHandler("delete_group", delete_group_cmd))
    app.add_handler(CommandHandler("my_groups", my_groups_cmd))
    app.add_handler(CommandHandler("add_lessons", add_lessons_cmd))
    app.add_handler(CommandHandler("delete_lesson", delete_lesson_cmd))
    app.add_handler(CommandHandler("lessons", lessons_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.job_queue.run_repeating(check_reminders, interval=CHECK_INTERVAL_SECONDS, first=5)

    logger.info("Bot Toshkent vaqti bilan muvaffaqiyatli ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
