import os
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
import pytz
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

import database as db

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TZ = pytz.timezone("Asia/Tashkent")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Conversation States
WAITING_GROUP_NAME, WAITING_LESSON_DATA = range(2)

# --- Helper: Google Calendar Link Generator ---
def create_gcal_link(title: str, start_dt: datetime, details: str = ""):
    end_dt = start_dt + timedelta(hours=1)
    fmt = "%Y%m%dT%H%M%SZ"
    
    # Convert local to UTC for Google Calendar Link
    start_utc = start_dt.astimezone(pytz.utc).strftime(fmt)
    end_utc = end_dt.astimezone(pytz.utc).strftime(fmt)
    
    base_url = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    url = f"{base_url}&text={quote(title)}&dates={start_utc}/{end_utc}&details={quote(details)}"
    return url

# --- Keyboards ---
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("📚 Mening Darslarim"), KeyboardButton("➕ Yangi Guruh Yaratish")],
        [KeyboardButton("⚙️ Guruhlarimni Boshqarish"), KeyboardButton("❓ Yordam")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Commands & Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Direct Invite Link via Deep Linking
    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if group:
            db.add_subscriber(user.id, group["id"])
            await update.message.reply_text(
                f"🎉 Siz **{group['name']}** guruhiga muvaffaqiyatli a'zo bo'ldingiz!\n\n"
                f"Endi darslar va eslatmalar ushbu bot orqali kelib turadi.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard()
            )
            return
        else:
            await update.message.reply_text("❌ Guruh topilmadi yoki havola eskirgan.")

    await update.message.reply_text(
        f"Xush kelibsiz, **{user.first_name}**! 👋\n\n"
        f"Bot orqali darslaringizni rejalashtiring va o'z vaqtida eslatmalar oling.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

# --- Group Creation (Conversation) ---
async def start_create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *Yangi guruh nomini kiriting:*\n\n"
        "Masalan: `Frontend React 12-guruh` yoki `Ingliz tili IELTS`",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_GROUP_NAME

async def save_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = update.message.text.strip()
    
    group = db.create_group(name, user.id)
    bot = await context.bot.get_me()
    invite_link = f"https://t.me/{bot.username}?start=g_{group['invite_code']}"

    text = (
        f"✅ **Guruh Yaratildi!**\n\n"
        f"📌 **Nomi:** {group['name']}\n"
        f"🔗 **A'zo bo'lish havolasi:**\n`{invite_link}`\n\n"
        f"Ushbu havolani o'quvchilaringizga ulashing."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{group['id']}")]
    ])

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    return ConversationHandler.END

# --- Manage Groups ---
async def show_managed_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_owned_groups(user.id)

    if not groups:
        await update.message.reply_text("Sizda hali yaratilgan guruhlar yo'q.")
        return

    keyboard = []
    for g in groups:
        keyboard.append([InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"managegroup_{g['id']}")])

    await update.message.reply_text(
        "⚙️ **Boshqarish uchun guruhni tanlang:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def group_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    bot = await context.bot.get_me()

    if data.startswith("managegroup_"):
        gid = int(data.split("_")[1])
        group = db.get_group(gid)
        invite_link = f"https://t.me/{bot.username}?start=g_{group['invite_code']}"
        
        text = (
            f"📌 **Guruh:** {group['name']}\n"
            f"🔗 **A'zolik havolasi:** `{invite_link}`\n\n"
            f"Kerakli amalni tanlang:"
        )
        
        btns = [
            [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{gid}")],
            [InlineKeyboardButton("📋 Darslar Ro'yxati / O'chirish", callback_data=f"listlessons_{gid}")],
            [InlineKeyboardButton("🗑 Guruhni O'chirish", callback_data=f"delgroup_{gid}")]
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("delgroup_"):
        gid = int(data.split("_")[1])
        db.delete_group(gid)
        await query.edit_message_text("🗑 Guruh va undagi barcha darslar o'chirildi.")

# --- Lesson Addition (Conversation) ---
async def start_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gid = int(query.data.split("_")[1])
    context.user_data["target_group_id"] = gid

    text = (
        "✍️ **Dars ma'lumotlarini quyidagi shaklda yuboring:**\n\n"
        "`Dars Mavzusi`\n"
        "`O'qituvchi Ismi`\n"
        "`Onlayn Dars Linki (bo'lsa, aks holda - qo'ying)`\n"
        "`YYYY-MM-DD HH:MM` (Sana va vaqt)\n\n"
        "📌 **Misol:**\n"
        "Python Boshlang'ich Dars\n"
        "Anvar Karimov\n"
        "https://zoom.us/j/123456789\n"
        "2026-08-15 19:00"
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return WAITING_LESSON_DATA

async def save_lesson_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = context.user_data.get("target_group_id")
    lines = [line.strip() for line in update.message.text.split("\n") if line.strip()]

    if len(lines) < 4:
        await update.message.reply_text("⚠️ Noto'g'ri format! Ma'lumotlar 4 ta qatordan iborat bo'lishi kerak. Qayta urinib ko'ring.")
        return WAITING_LESSON_DATA

    title, teacher, link, date_str = lines[0], lines[1], lines[2], lines[3]

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        start_iso = dt.strftime("%Y-%m-%d %H:%M:00")
    except ValueError:
        await update.message.reply_text("⚠️ Sana vaqt formati xato! `YYYY-MM-DD HH:MM` ko'rinishida yozing (Masalan: `2026-08-15 19:00`).")
        return WAITING_LESSON_DATA

    db.add_lesson(
        group_id=gid,
        title=title,
        teacher=teacher,
        meeting_link="" if link == "-" else link,
        start_time_iso=start_iso
    )

    await update.message.reply_text("✅ **Dars muvaffaqiyatli qo'shildi!**", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- Student Lesson Viewing ---
async def show_student_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_subscribed_groups(user.id)

    if not groups:
        await update.message.reply_text("Siz hech qaysi guruhga a'zo emassiz.")
        return

    has_lessons = False
    for g in groups:
        lessons = db.get_upcoming_lessons_for_group(g["id"])
        if not lessons:
            continue
        
        has_lessons = True
        for l in lessons:
            dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
            dt_loc = TZ.localize(dt_naive)
            gcal_link = create_gcal_link(l["title"], dt_loc, f"O'qituvchi: {l['teacher']}")

            text = (
                f"📚 **Guruh:** {g['name']}\n"
                f"📖 **Dars:** {l['title']}\n"
                f"👤 **Ustoz:** {l['teacher']}\n"
                f"📅 **Vaqti:** {dt_loc.strftime('%d.%m.%Y %H:%M')}"
            )

            btns = [[InlineKeyboardButton("📅 Google Kalendarga qo'shish", url=gcal_link)]]
            if l["meeting_link"]:
                btns.append([InlineKeyboardButton("🔗 Onlayn Darsga Kirish", url=l["meeting_link"])])

            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

    if not has_lessons:
        await update.message.reply_text("Yaqin orada rejalashtirilgan darslar yo'q.")

# --- Lesson Management (List / Delete) ---
async def list_lessons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gid = int(query.data.split("_")[1])
    lessons = db.get_upcoming_lessons_for_group(gid)

    if not lessons:
        await query.message.reply_text("Ushbu guruhda darslar mavjud emas.")
        return

    for l in lessons:
        dt = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
        text = f"📖 **{l['title']}**\n🗓 {dt.strftime('%d.%m.%Y %H:%M')}"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 O'chirish", callback_data=f"dellesson_{l['id']}")]])
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=btn)

async def delete_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lid = int(query.data.split("_")[1])
    db.delete_lesson(lid)
    await query.edit_message_text("🗑 Dars o'chirildi.")

# --- Background Task: Reminders ---
async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = db.get_now()
    lessons = db.get_all_future_lessons()

    reminder_rules = [
        ("1d", timedelta(days=1), "1 kun"),
        ("2h", timedelta(hours=2), "2 soat"),
        ("15m", timedelta(minutes=15), "15 daqiqa"),
        ("now", timedelta(minutes=0), "Boshlandi")
    ]

    for l in lessons:
        dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
        start_dt = TZ.localize(dt_naive)

        for code, offset, label in reminder_rules:
            if db.was_reminder_sent(l["id"], code):
                continue

            target_time = start_dt - offset
            # 2 minutlik oyna ichida tekshiramiz
            if target_time <= now < target_time + timedelta(minutes=2):
                subscribers = db.get_subscribers(l["group_id"])
                
                if code == "now":
                    msg = f"🔴 **Dars boshlandi!**\n\n📖 **{l['title']}**\n👤 Ustoz: {l['teacher']}"
                else:
                    msg = f"⏰ **Eslatma:** Darsga **{label}** qoldi!\n\n📖 **{l['title']}**\n👤 Ustoz: {l['teacher']}\n🕐 Vaqti: {start_dt.strftime('%H:%M')}"

                btns = []
                if l["meeting_link"]:
                    btns.append([InlineKeyboardButton("🔗 Darsga kirish", url=l["meeting_link"])])
                
                markup = InlineKeyboardMarkup(btns) if btns else None

                for uid in subscribers:
                    try:
                        await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
                    except Exception:
                        pass

                db.mark_reminder_sent(l["id"], code)

# --- Main App ---
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN o'zgaruvchisi o'rnatilmagan!")

    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Group creation conversation
    create_group_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Yangi Guruh Yaratish$"), start_create_group)],
        states={
            WAITING_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_name)]
        },
        fallbacks=[]
    )

    # Lesson addition conversation
    add_lesson_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_lesson, pattern="^addlesson_")],
        states={
            WAITING_LESSON_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_lesson_data)]
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)
    
    app.add_handler(MessageHandler(filters.Regex("^📚 Mening Darslarim$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Guruhlarimni Boshqarish$"), show_managed_groups))
    
    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_)"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^dellesson_"))

    # Background Job (Reminders every 60 seconds)
    app.job_queue.run_repeating(check_and_send_reminders, interval=60, first=10)

    logger = logging.getLogger(__name__)
    logger.info("Zamonaviy Bot Ishga Tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
