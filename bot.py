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

# Conversation xolatlari
WAIT_GROUP_NAME, WAIT_BULK_LESSONS = range(2)

# --- Google Calendar havolasini yaratish ---
def create_gcal_link(title: str, start_dt: datetime, details: str = ""):
    end_dt = start_dt + timedelta(hours=1)
    fmt = "%Y%m%dT%H%M%SZ"
    start_utc = start_dt.astimezone(pytz.utc).strftime(fmt)
    end_utc = end_dt.astimezone(pytz.utc).strftime(fmt)
    base_url = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    return f"{base_url}&text={quote(title)}&dates={start_utc}/{end_utc}&details={quote(details)}"

# --- Asosiy menyu tugmalari ---
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("📚 Mening Darslarim"), KeyboardButton("⚙️ Eslatma Sozlamalari")],
        [KeyboardButton("➕ Yangi Guruh Yaratish"), KeyboardButton("📂 Guruhlarimni Boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Buyruqlar va Ishlovchilar ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Taklif havolasi orqali kirish
    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if group:
            db.add_subscriber(user.id, group["id"])
            await update.message.reply_text(
                f"🎉 Siz **{group['name']}** guruhiga muvaffaqiyatli a'zo bo'ldingiz!\n\n"
                f"Endi dars eslatmalari to'g'ridan-to'g'ri ushbu shaxsiy chatga kelib turadi.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard()
            )
            return
        else:
            await update.message.reply_text("❌ Guruh topilmadi yoki havola eskirgan.")

    db.add_subscriber(user.id, 0)
    await update.message.reply_text(
        f"Xush kelibsiz, **{user.first_name}**! 👋\n\n"
        f"Bot orqali darslaringizni rejalashtiring va eslatmalarni o'zingizga moslab sozlang.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

# --- Eslatmalarni sozlash ---
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    st = db.get_user_settings(user.id)

    def icon(val): return "✅" if val == 1 else "❌"

    text = (
        "⚙️ **Eslatma Sozlamalari**\n\n"
        "Qaysi vaqtlarda sizga shaxsiy eslatma kelishini tanlang:\n"
        "Tugmani bir marta bosish orqali Yoqish (✅) yoki O'chirish (❌) mumkin."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{icon(st['rem_24h'])} 1 kun (24 soat) oldin", callback_data="toggle_24h")],
        [InlineKeyboardButton(f"{icon(st['rem_12h'])} 12 soat oldin", callback_data="toggle_12h")],
        [InlineKeyboardButton(f"{icon(st['rem_6h'])} 6 soat oldin", callback_data="toggle_6h")],
        [InlineKeyboardButton(f"{icon(st['rem_1h'])} 1 soat oldin", callback_data="toggle_1h")],
        [InlineKeyboardButton(f"{icon(st['rem_15m'])} 15 daqiqa oldin", callback_data="toggle_15m")],
        [InlineKeyboardButton(f"{icon(st['rem_now'])} 🔴 Dars Boshlanganda", callback_data="toggle_now")]
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    r_type = query.data.replace("toggle_", "")
    db.toggle_user_setting(query.from_user.id, r_type)
    await show_settings(update, context)

# --- Guruh yaratish ---
async def start_create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *Yangi guruh nomini kiriting:*\n\nMasalan: `Frontend React 12-guruh`",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAIT_GROUP_NAME

async def save_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = update.message.text.strip()
    group = db.create_group(name, user.id)
    bot = await context.bot.get_me()
    invite_link = f"https://t.me/{bot.username}?start=g_{group['invite_code']}"

    text = (
        f"✅ **Guruh Yaratildi!**\n\n"
        f"📌 **Nomi:** {group['name']}\n"
        f"🔗 **A'zolik havolasi:**\n`{invite_link}`\n\n"
        f"Ushbu havolani o'quvchilaringizga ulashing."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{group['id']}")]
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    return ConversationHandler.END

# --- Bitta yoki Ko'p Darslarni Bittalab/Ommaviy Qo'shish ---
async def start_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["target_group_id"] = gid

    text = (
        "✍️ **Dars ma'lumotlarini kiriting!**\n\n"
        "Bitta darsni yoki **20-30 ta darsni bitta xabarda** yuborishingiz mumkin.\n"
        "Ko'p dars yuborayotganda darslar orasiga **`---`** (3 ta chiziq) qo'ying.\n\n"
        "📌 **Har bir dars formati:**\n"
        "`Dars Nomi`\n"
        "`Ustoz Ismi`\n"
        "`Zoom/Meet Linki (bo'lmasa - deb yozing)`\n"
        "`YYYY-MM-DD HH:MM` (Sana va Vaqt)\n\n"
        "👇 **Namuna (Ko'p darslar uchun):**\n"
        "1-Dars: Kirish\n"
        "Anvar Karimov\n"
        "https://zoom.us/j/123456\n"
        "2026-08-01 19:00\n"
        "---\n"
        "2-Dars: O'zgaruvchilar\n"
        "Anvar Karimov\n"
        "-\n"
        "2026-08-03 19:00"
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return WAIT_BULK_LESSONS

async def save_bulk_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    gid = context.user_data.get("target_group_id")

    blocks = raw_text.split("---")
    added_count = 0
    errors = []

    for idx, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            continue
        
        if len(lines) < 4:
            errors.append(f"❌ {idx}-darsda qatorlar yetarli emas (4 ta qator bo'lishi kerak)")
            continue

        title, teacher, link, date_str = lines[0], lines[1], lines[2], lines[3]
        meeting_link = "" if link == "-" else link

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            start_iso = dt.strftime("%Y-%m-%d %H:%M:00")
        except ValueError:
            errors.append(f"❌ {idx}-darsda sana formati xato: '{date_str}' (To'g'ri format: YYYY-MM-DD HH:MM)")
            continue

        db.add_lesson(
            group_id=gid,
            title=title,
            teacher=teacher,
            meeting_link=meeting_link,
            start_time_iso=start_iso
        )
        added_count += 1

    reply_msg = f"✅ **Jami {added_count} ta dars muvaffaqiyatli qo'shildi!**"
    if errors:
        reply_msg += "\n\n⚠️ **Ba'zi darslarda xatolik bor:**\n" + "\n".join(errors)

    await update.message.reply_text(reply_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- Darslarni ko'rish ---
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
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

    if not has_lessons:
        await update.message.reply_text("Yaqin orada rejalashtirilgan darslar yo'q.")

# --- Guruhlarni boshqarish ---
async def show_managed_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_owned_groups(user.id)

    if not groups:
        await update.message.reply_text("Sizda hali yaratilgan guruhlar yo'q.")
        return

    keyboard = [[InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"managegroup_{g['id']}")] for g in groups]
    await update.message.reply_text("⚙️ **Boshqarish uchun guruhni tanlang:**", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def group_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    bot = await context.bot.get_me()

    if data.startswith("managegroup_"):
        gid = int(data.split("_")[1])
        group = db.get_group(gid)
        invite_link = f"https://t.me/{bot.username}?start=g_{group['invite_code']}"
        text = f"📌 **Guruh:** {group['name']}\n🔗 **A'zolik havolasi:** `{invite_link}`"
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

# --- Fonga o'rnatilgan eslatish tizimi ---
async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = db.get_now()
    lessons = db.get_all_future_lessons()

    reminder_rules = [
        ("24h", timedelta(days=1), "1 kun (24 soat)"),
        ("12h", timedelta(hours=12), "12 soat"),
        ("6h", timedelta(hours=6), "6 soat"),
        ("1h", timedelta(hours=1), "1 soat"),
        ("15m", timedelta(minutes=15), "15 daqiqa"),
        ("now", timedelta(minutes=0), "Boshlandi")
    ]

    for l in lessons:
        dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
        start_dt = TZ.localize(dt_naive)

        for code, offset, label in reminder_rules:
            target_time = start_dt - offset
            
            if target_time <= now < target_time + timedelta(minutes=2):
                subscribers = db.get_subscribers(l["group_id"])
                
                for uid in subscribers:
                    if db.was_reminder_sent(l["id"], uid, code):
                        continue

                    st = db.get_user_settings(uid)
                    if st.get(f"rem_{code}", 1) == 0:
                        continue 

                    if code == "now":
                        msg = f"🔴 **DARS BOSHLANDI!**\n\n📖 **{l['title']}**\n👤 Ustoz: {l['teacher']}\n⏰ Vaqti: {start_dt.strftime('%H:%M')}"
                    else:
                        msg = f"⏰ **ESLATMA:** Darsga **{label}** qoldi!\n\n📖 **{l['title']}**\n👤 Ustoz: {l['teacher']}\n🕐 Vaqti: {start_dt.strftime('%d.%m.%Y %H:%M')}"

                    btns = []
                    if code == "now" and l["meeting_link"]:
                        btns.append([InlineKeyboardButton("🔗 Darsga kirish (Zoom/Meet)", url=l["meeting_link"])])

                    markup = InlineKeyboardMarkup(btns) if btns else None

                    try:
                        await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
                        db.mark_reminder_sent(l["id"], uid, code)
                    except Exception:
                        pass

# --- Asosiy Dastur ---
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN o'zgaruvchisi topilmadi!")

    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    create_group_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Yangi Guruh Yaratish$"), start_create_group)],
        states={
            WAIT_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_name)]
        },
        fallbacks=[]
    )

    add_lesson_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_lesson, pattern="^addlesson_")],
        states={
            WAIT_BULK_LESSONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bulk_lessons)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)

    app.add_handler(MessageHandler(filters.Regex("^⚙️ Eslatma Sozlamalari$"), show_settings))
    app.add_handler(CallbackQueryHandler(toggle_setting_callback, pattern="^toggle_"))

    app.add_handler(MessageHandler(filters.Regex("^📚 Mening Darslarim$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex("^📂 Guruhlarimni Boshqarish$"), show_managed_groups))

    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_)"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^dellesson_"))

    app.job_queue.run_repeating(check_and_send_reminders, interval=60, first=10)

    logger = logging.getLogger(__name__)
    logger.info("Bot tayyor va ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
