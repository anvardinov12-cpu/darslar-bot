import os
import io
import logging
from datetime import datetime, timedelta
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

# ⚠️ O'ZINGIZNING TELEGRAM ID'INGIZNI SHU YERGA YOZING:
SUPER_ADMIN_ID = 355784505

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Conversation States
WAIT_GROUP_NAME = 1
WAIT_BULK_LESSONS = 2

# --- ICS Calendar Generator (With Phone Alarms) ---
def generate_ics_calendar(group_name: str, lessons: list) -> io.BytesIO:
    ics_content = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Dars Eslatuvchi Bot//UZ",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{group_name}"
    ]

    for l in lessons:
        dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
        # Tashkent (UTC+5) vaqtini UTC ga o'tkazamiz
        dt_utc = dt_naive - timedelta(hours=5)
        dt_start_str = dt_utc.strftime("%Y%m%dT%H%M%SZ")
        dt_end_str = (dt_utc + timedelta(hours=1, minutes=30)).strftime("%Y%m%dT%H%M%SZ")

        summary = l["title"]
        description = f"Ustoz: {l['teacher']}"
        # sqlite3.Row uchun xatosiz kalit olish:
        location = l["meeting_link"] if l["meeting_link"] else ""

        ics_content.extend([
            "BEGIN:VEVENT",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            f"DTSTART:{dt_start_str}",
            f"DTEND:{dt_end_str}",
            f"UID:lesson_{l['id']}@darsbot",
            
            # Telefon kalendarining ichki eslatmalari (VALARM):
            "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Darsga 1 kun qoldi!\nTRIGGER:-P1D\nEND:VALARM",
            "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Darsga 1 soat qoldi!\nTRIGGER:-PT1H\nEND:VALARM",
            "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Darsga 15 daqiqa qoldi!\nTRIGGER:-PT15M\nEND:VALARM",
            "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Dars boshlandi!\nTRIGGER:PT0M\nEND:VALARM",

            "END:VEVENT"
        ])

    ics_content.append("END:VCALENDAR")
    file_bytes = "\r\n".join(ics_content).encode('utf-8')
    bio = io.BytesIO(file_bytes)
    bio.name = f"{group_name}_darslar.ics"
    return bio
# --- Keyboards ---
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("📚 Mening Darslarim"), KeyboardButton("⚙️ Eslatma Sozlamalari")],
        [KeyboardButton("➕ Yangi Guruh Yaratish"), KeyboardButton("📂 Guruhlarimni Boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Start & Deep Linking ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if group:
            db.add_subscriber(user.id, group["id"])
            await update.message.reply_text(
                f"🎉 Siz **{group['name']}** guruhiga muvaffaqiyatli a'zo bo'ldingiz!\n\n"
                f"Dars eslatmalari shaxsiy lichkangizga yuboriladi.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard()
            )
            return
        else:
            await update.message.reply_text("❌ Guruh topilmadi yoki havola eskirgan.")

    db.add_subscriber(user.id, 0)
    await update.message.reply_text(
        f"Xush kelibsiz, **{user.first_name}**! 👋\n\n"
        f"Bot orqali darslaringizni kuzatib boring va eslatmalarni o'zingizga moslang.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

# --- Settings ---
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    st = db.get_user_settings(user.id)

    def icon(val): return "✅" if val == 1 else "❌"

    text = (
        "⚙️ **Eslatma Sozlamalari**\n\n"
        "Qaysi vaqtlarda shaxsiy lichkangizga eslatma kelishini tanlang:\n"
        "Yoqish yoki o'chirish uchun bir marta bosing."
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

# --- Create Group ---
cancel_keyboard = ReplyKeyboardMarkup([["⬅️ Orqaga"]], resize_keyboard=True)

async def start_create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruh yaratish jarayonini boshlash"""
    await update.message.reply_text(
        "📝 Yangi guruh nomini kiriting:\n\n"
        "(Bekor qilish uchun '⬅️ Orqaga' tugmasini bosing)",
        reply_markup=cancel_keyboard
    )
    return WAIT_GROUP_NAME

async def cancel_group_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jarayonni bekor qilish va asosiy menyuga qaytarish"""
    context.user_data.clear()
    
    main_menu = ReplyKeyboardMarkup([
        ["📚 Mening Darslarim", "⚙️ Eslatma Sozlamalari"],
        ["➕ Yangi Guruh Yaratish", "📂 Guruhlarimni Boshqarish"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "❌ Jarayon bekor qilindi.",
        reply_markup=main_menu
    )
    return ConversationHandler.END

async def save_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruh nomini saqlash"""
    try:
        group_name = update.message.text.strip()
        user_id = update.effective_user.id

        # Ma'lumotlar bazasiga saqlaymiz
        db.add_group(user_id, group_name)

        main_menu = ReplyKeyboardMarkup([
            ["📚 Mening Darslarim", "⚙️ Eslatma Sozlamalari"],
            ["➕ Yangi Guruh Yaratish", "📂 Guruhlarimni Boshqarish"]
        ], resize_keyboard=True)

        await update.message.reply_text(
            f"✅ **{group_name}** guruhi muvaffaqiyatli yaratildi!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu
        )
        return ConversationHandler.END

    except Exception as e:
        print(f"Guruh saqlashda xatolik: {e}")
        await update.message.reply_text(
            f"⚠️ Guruhni saqlashda xatolik yuz berdi:\n`{e}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
# --- Bulk Add Lessons (1 Oylik / 20 ta Darsni Bittada Qo'shish) ---
async def start_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["target_group_id"] = gid

    text = (
        "✍️ **Darslarni bitta yoki bir vaqtda ko'plab (masalan, 20 ta) yuboring!**\n\n"
        "Har bir dars orasiga **`---`** (3 ta chiziq) qo'yib yuboring.\n\n"
        "📌 **Har bir dars formati:**\n"
        "`Dars Nomi`\n"
        "`Ustoz Ismi`\n"
        "`Zoom Link (yoki link bo'lmasa - qo'ying)`\n"
        "`YYYY-MM-DD HH:MM`\n\n"
        "👇 **Namuna:**\n"
        "`1-Dars: Kirish`\n"
        "`Anvar Karimov`\n"
        "`https://zoom.us/j/12345`\n"
        "`2026-08-01 19:00`\n"
        "----\n"
        "`2-Dars: O'zgaruvchilar`\n"
        "`Anvar Karimov`\n"
        "`-`\n"
        "`2026-08-03 19:00`"
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return WAIT_BULK_LESSONS

async def process_bulk_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            errors.append(f"❌ {idx}-darsda qatorlar yetarli emas (4 qator bo'lishi kerak)")
            continue

        title, teacher, link, date_str = lines[0], lines[1], lines[2], lines[3]
        meeting_link = "" if link == "-" else link

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            start_iso = dt.strftime("%Y-%m-%d %H:%M:00")
        except ValueError:
            errors.append(f"❌ {idx}-darsda vaqt xato: '{date_str}'")
            continue

        db.add_lesson(group_id=gid, title=title, teacher=teacher, meeting_link=meeting_link, start_time_iso=start_iso)
        added_count += 1

    reply_msg = f"✅ **Jami {added_count} ta dars muvaffaqiyatli qo'shildi!**"
    if errors:
        reply_msg += "\n\n⚠️ **Quyidagilarda xatolik bor:**\n" + "\n".join(errors)

    await update.message.reply_text(reply_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- Display Lessons per Group (Single Message + ICS Download) ---
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
        text = f"📚 **Guruh: {g['name']}**\n"
        text += f"📋 **Rejalashtirilgan darslar ({len(lessons)} ta):**\n\n"

        for idx, l in enumerate(lessons, start=1):
            dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
            dt_loc = TZ.localize(dt_naive)

            text += (
                f"**{idx}. {l['title']}**\n"
                f"👤 Ustoz: {l['teacher']}\n"
                f"📅 Vaqti: {dt_loc.strftime('%d.%m.%Y %H:%M')}\n\n"
            )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Barcha darslarni kalendarga saqlash (.ics)", callback_data=f"download_ics_{g['id']}")]
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    if not has_lessons:
        await update.message.reply_text("Yaqin orada rejalashtirilgan darslar yo'q.")

async def ics_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ .ics fayli tayyorlanmoqda...") # O'quvchiga darhol kichik xabar chiqadi

    try:
        data_parts = query.data.split("_")
        group_id = int(data_parts[2])

        group = db.get_group(group_id)
        lessons = db.get_upcoming_lessons_for_group(group_id)

        if not lessons:
            await query.message.reply_text("❌ Ushbu guruhda darslar topilmadi.")
            return

        # ICS faylini yaratamiz
        ics_file = generate_ics_calendar(group["name"], lessons)

        # Faylni yuboramiz
        await query.message.reply_document(
            document=ics_file,
            filename=f"{group['name']}_darslar.ics",
            caption=f"📅 **{group['name']}** guruhining darslar kalendari fayli.\n\nFaylni ochib, kalendaringizga saqlab oling!",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"ICS Yuborishda xatolik: {e}")
        await query.message.reply_text(f"⚠️ Faylni yuklashda xatolik yuz berdi: {e}")

# --- Group Management ---
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
        await query.edit_message_text("🗑 Guruh va undagi darslar o'chirildi.")

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

# --- SUPER ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != SUPER_ADMIN_ID:
        await update.message.reply_text("⛔️ Ushbu bo'lim faqat Bosh Admin uchun!")
        return

    total_users, total_groups, total_lessons = db.get_total_stats()
    text = (
        "👑 **SUPER ADMIN PANEL**\n\n"
        f"📊 **Statistika:**\n"
        f"• Barcha obunachilar: **{total_users} ta**\n"
        f"• Jami guruhlar: **{total_groups} ta**\n"
        f"• Faol darslar: **{total_lessons} ta**"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👥 Barcha Obunachilar Ro'yxati", callback_data="admin_all_users")]])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != SUPER_ADMIN_ID:
        return

    if query.data == "admin_all_users":
        user_ids = db.get_all_users_list()
        if not user_ids:
            await query.message.reply_text("Obunachilar topilmadi.")
            return

        text = f"👥 **Barcha Bot Obunachilari ({len(user_ids)} ta):**\n\n"
        for idx, uid in enumerate(user_ids, start=1):
            try:
                chat = await context.bot.get_chat(uid)
                full_name = chat.full_name or "Foydalanuvchi"
                uname = f" (@{chat.username})" if chat.username else ""
                text += f"{idx}. {full_name}{uname} — `ID: {uid}`\n"
            except Exception:
                text += f"{idx}. ID: `{uid}`\n"

        if len(text) > 4000:
            for x in range(0, len(text), 4000):
                await query.message.reply_text(text[x:x+4000], parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# --- Background Reminder Engine ---
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
                        msg = f"🔴 **DARS BO'SHLANDI!**\n\n📖 **{l['title']}**\n👤 Ustoz: {l['teacher']}\n⏰ Vaqti: {start_dt.strftime('%H:%M')}"
                    else:
                        msg = f"⏰ **ESLATMA:** Darsga **{label}** qoldi!\n\n📖 **{l['title']}**\n👤 Ustoz: {l['teacher']}\n🕐 Vaqti: {start_dt.strftime('%d.%m.%Y %H:%M')}"

                    btns = []
                    # Zoom link FAQA T dars boshlanganda keladi!
                    if code == "now" and l["meeting_link"]:
                        btns.append([InlineKeyboardButton("🔗 Darsga kirish (Zoom/Meet)", url=l["meeting_link"])])

                    markup = InlineKeyboardMarkup(btns) if btns else None

                    try:
                        await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
                        db.mark_reminder_sent(l["id"], uid, code)
                    except Exception:
                        pass

# --- Main App ---
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN mavjud emas!")

    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    create_group_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Yangi Guruh Yaratish$"), start_create_group)],
        states={
            WAIT_GROUP_NAME: [
                MessageHandler(filters.Regex("^⬅️ Orqaga$"), cancel_group_creation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_name)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_group_creation),
            MessageHandler(filters.Regex("^⬅️ Orqaga$"), cancel_group_creation)
        ]
    )

    add_lesson_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_lesson, pattern="^addlesson_")],
        states={
            WAIT_BULK_LESSONS: [
                MessageHandler(filters.Regex("^⬅️ Orqaga$"), cancel_group_creation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_bulk_lessons)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_group_creation),
            MessageHandler(filters.Regex("^⬅️ Orqaga$"), cancel_group_creation)
        ]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)

    app.add_handler(MessageHandler(filters.Regex("^⚙️ Eslatma Sozlamalari$"), show_settings))
    app.add_handler(MessageHandler(filters.Regex("^📚 Mening Darslarim$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex("^📂 Guruhlarimni Boshqarish$"), show_managed_groups))

    app.add_handler(CallbackQueryHandler(toggle_setting_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(ics_download_callback, pattern="^download_ics_"))
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_)"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^dellesson_"))

    app.job_queue.run_repeating(check_and_send_reminders, interval=60, first=10)

    app.run_polling()
    
if __name__ == "__main__":
    main()
