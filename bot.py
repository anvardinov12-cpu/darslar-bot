import os
import io
import logging
import html
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import asyncio
import sys

if sys.platform != "win32":
    try:
        asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
        
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
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

SUPER_ADMIN_ID = 355784505

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# States
WAIT_GROUP_NAME = 1
WAIT_BULK_LESSONS = 2
BROADCAST_WAIT_MSG = 100
GROUP_ANNOUNCE_WAIT_MSG = 101
WAIT_DAY_SCHEDULE = 3
WAIT_CURRICULUM_ITEM = 4


# --- Background Reminder Checker ---
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now(TZ)
        lessons = db.get_all_future_lessons()
        if not lessons:
            return
        
        for l in lessons:
            try:
                lesson_id = l["id"]
                group_id = l["group_id"]
                group = db.get_group(group_id)
                if not group:
                    continue
                    
                dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
                dt_lesson = TZ.localize(dt_naive)
                
                diff_minutes = (dt_lesson - now).total_seconds() / 60.0
                
                # ==========================================
                # 1-QISM: REAL TELEGRAM GURUHGA YUBORISH
                # ==========================================
                chat_id = group["chat_id"] if group else None
                    
                if chat_id:
                    async def send_group_reminder(r_type, text_prefix, title_prefix="🔔 **DARS ESLATMASI!**", include_link=False):
                        if not db.was_reminder_sent(lesson_id, chat_id, r_type):
                            try:
                                link_text = f"🔗 **Havola:** {l['meeting_link']}\n" if (include_link and l['meeting_link']) else ""
                                msg = (
                                    f"{title_prefix}\n\n"
                                    f"📚 Guruh: **{group['name']}**\n"
                                    f"📖 Dars: **{l['title']}**\n"
                                    f"👤 Ustoz: {l['teacher']}\n"
                                    f"📅 Vaqti: {dt_naive.strftime('%d.%m.%Y %H:%M')}\n"
                                    f"{link_text}\n"
                                    f"*{text_prefix}*"
                                )
                                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
                                db.mark_reminder_sent(lesson_id, chat_id, r_type)
                            except Exception as e:
                                logging.error(f"Guruhga xabar yuborishda xatolik ({chat_id}): {e}")

                    if 175 <= diff_minutes <= 185:
                        await send_group_reminder("grp_3h", "Darsga 3 soat qoldi!", include_link=False)
                    elif 55 <= diff_minutes <= 65:
                        await send_group_reminder("grp_1h", "Darsga 1 soat qoldi!", include_link=False)
                    elif 12 <= diff_minutes <= 18:
                        await send_group_reminder("grp_15m", "Darsga 15 daqiqa qoldi!", include_link=True)
                    elif -2 <= diff_minutes <= 3:
                        await send_group_reminder("grp_now", "🔴 Dars boshlandi, darsga kiring!", title_prefix="🔴 **DARS BOSHLANDI!**", include_link=True)

                # ==========================================
                # 2-QISM: O'QUVCHILARGA SHAXSIY YUBORISH
                # ==========================================
                subscribers = db.get_subscribers(group_id)
                if subscribers:
                    for sub in subscribers:
                        user_id = sub["user_id"]
                        if user_id == 0:
                            continue
                        settings = db.get_user_settings(user_id)
                        if not settings:
                            continue
                        
                        async def send_if_needed(r_type, text_prefix, title_prefix="🔔 **DARS ESLATMASI!**", include_link=False):
                            if not db.was_reminder_sent(lesson_id, user_id, r_type):
                                try:
                                    link_text = f"🔗 **Havola:** {l['meeting_link']}\n" if (include_link and l['meeting_link']) else ""
                                    msg = (
                                        f"{title_prefix}\n\n"
                                        f"📚 Guruh: **{group['name']}**\n"
                                        f"📖 Dars: **{l['title']}**\n"
                                        f"👤 Ustoz: {l['teacher']}\n"
                                        f"📅 Vaqti: {dt_naive.strftime('%d.%m.%Y %H:%M')}\n"
                                        f"{link_text}\n"
                                        f"*{text_prefix}*"
                                    )
                                    await context.bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.MARKDOWN)
                                    db.mark_reminder_sent(lesson_id, user_id, r_type)
                                except Exception as e:
                                    logging.error(f"Lichkaga yuborishda xatolik ({user_id}): {e}")

                        if settings.get("rem_24h", 1) == 1 and 1435 <= diff_minutes <= 1445:
                            await send_if_needed("24h", "Darsga 24 soat qoldi!", include_link=False)
                        elif settings.get("rem_12h", 1) == 1 and 715 <= diff_minutes <= 725:
                            await send_if_needed("12h", "Darsga 12 soat qoldi!", include_link=False)
                        elif settings.get("rem_6h", 1) == 1 and 355 <= diff_minutes <= 365:
                            await send_if_needed("6h", "Darsga 6 soat qoldi!", include_link=False)
                        elif settings.get("rem_3h", 1) == 1 and 175 <= diff_minutes <= 185:
                            await send_if_needed("3h", "Darsga 3 soat qoldi!", include_link=False)
                        elif settings.get("rem_1h", 1) == 1 and 55 <= diff_minutes <= 65:
                            await send_if_needed("1h", "Darsga 1 soat qoldi!", include_link=False)
                        elif settings.get("rem_15m", 1) == 1 and 12 <= diff_minutes <= 18:
                            await send_if_needed("15m", "Darsga 15 daqiqa qoldi!", include_link=True)
                        elif settings.get("rem_now", 1) == 1 and -2 <= diff_minutes <= 3:
                            await send_if_needed("now", "🔴 Dars boshlandi, darsga kiring!", title_prefix="🔴 **DARS BOSHLANDI!**", include_link=True)
            except Exception as lesson_err:
                logging.error(f"Darsni qayta ishlashda xatolik (ID: {l.get('id')}): {lesson_err}")
    except Exception as e:
        logging.error(f"check_reminders umumiy xatolik: {e}")

# --- ICS Calendar Generator ---
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
        dt_local = TZ.localize(dt_naive)
        dt_utc = dt_local.astimezone(pytz.utc) 
        
        dt_start_str = dt_utc.strftime("%Y%m%dT%H%M%SZ")
        dt_end_str = (dt_utc + timedelta(hours=1, minutes=30)).strftime("%Y%m%dT%H%M%SZ")

        summary = l["title"]
        description = f"Ustoz: {l['teacher']}"
        location = l["meeting_link"] if l["meeting_link"] else ""

        ics_content.extend([
            "BEGIN:VEVENT",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            f"DTSTART:{dt_start_str}",
            f"DTEND:{dt_end_str}",
            f"UID:lesson_{l['id']}@darsbot",
            "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Darsga 1 kun qoldi!\nTRIGGER:-P1D\nEND:VALARM",
            "BEGIN:VALARM\nACTION:DISPLAY\nDESCRIPTION:Darsga 3 soat qoldi!\nTRIGGER:-PT3H\nEND:VALARM",
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
BTN_LESSONS = "📚 Mening Darslarim"
BTN_SUBSCRIPTIONS = "📋 Obunalarim"
BTN_SETTINGS = "⚙️ Eslatma Sozlamalari 🔔"
BTN_CREATE_GROUP = "➕ Yangi Guruh Ochish"
BTN_MANAGE_GROUPS = "📂 Guruhlarimni Boshqarish"
BTN_GUIDE = "📖 Foydalanish tartibi"
BTN_BACK = "⬅️ Orqaga"

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_LESSONS), KeyboardButton(BTN_SUBSCRIPTIONS)],
            [KeyboardButton(BTN_CREATE_GROUP), KeyboardButton(BTN_MANAGE_GROUPS)],
            [KeyboardButton(BTN_SETTINGS), KeyboardButton(BTN_GUIDE)]
        ],
        resize_keyboard=True
    )

cancel_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_BACK)]],
    resize_keyboard=True
)

# --- Start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    message = update.message

    if message.chat.type in ["group", "supergroup"]:
        return

    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if group:
            db.add_subscriber(user.id, group["id"], user.first_name)
            await message.reply_text(
                f"🎉 Siz **{group['name']}** guruhiga muvaffaqiyatli a'zo bo'ldingiz!\n\n"
                f"Dars eslatmalari darsingizdan 1 kun, 12, 6, 1 soat, 15 daqiqa avval va dars boshlanganida yuboriladi.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard()
            )
            return
        else:
            await message.reply_text("❌ Guruh topilmadi yoki havola eskirgan.", reply_markup=main_menu_keyboard())

    db.add_subscriber(user.id, 0, user.first_name)
    await message.reply_text(
        f"Xush kelibsiz, **{user.first_name}**! 👋\n\n"
        f"Bot orqali darslaringizni kuzatib boring va eslatmalarni o'zingizga moslang.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **BOTDAN FOYDALANISH YO'RIQNOMASI**\n\n"
        "Botimizdan quyidagi **2 xil yo'nalishda** foydalanishingiz mumkin:\n\n"
        "1️⃣ **Oddiy o'quvchi / Talaba uchun:**\n"
        "• Ustozingiz yoki adminingiz bergan maxsus **havola (link)** ustiga bosing.\n"
        "• Botga kirib guruhga a'zo bo'lasiz.\n"
        "• Dars vaqti yaqinlashganda bot eslatma va havolalarni yuboradi.\n\n"
        "2️⃣ **Admin / O'qituvchi uchun:**\n"
        "• Menyudagi **'➕ Yangi Guruh Ochish'** tugmasini bosing.\n"
        "• **'📂 Guruhlarimni Boshqarish'** bo'limidan darslar qo'shing."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    st = db.get_user_settings(user.id)

    def icon(val): return "✅" if val == 1 else "❌"

    text = "⚙️🔔 **Eslatma Sozlamalari**\n\nQaysi vaqtlarda eslatma kelishini tanlang:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{icon(st['rem_24h'])} 1 kun oldin", callback_data="toggle_24h")],
        [InlineKeyboardButton(f"{icon(st['rem_12h'])} 12 soat oldin", callback_data="toggle_12h")],
        [InlineKeyboardButton(f"{icon(st['rem_6h'])} 6 soat oldin", callback_data="toggle_6h")],
        [InlineKeyboardButton(f"{icon(st['rem_1h'])} 1 soat oldin", callback_data="toggle_1h")],
        [InlineKeyboardButton(f"{icon(st['rem_15m'])} 15 daqiqa oldin", callback_data="toggle_15m")],
        [InlineKeyboardButton(f"{icon(st['rem_now'])} 🔴 Dars Boshlanganda", callback_data="toggle_now")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception:
            pass
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    r_type = query.data.replace("toggle_", "")
    db.toggle_user_setting(query.from_user.id, r_type)
    await show_settings(update, context)

async def start_create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Yangi guruh nomini kiriting:", reply_markup=cancel_keyboard)
    return WAIT_GROUP_NAME

async def cancel_group_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Jarayon bekor qilindi.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def save_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        group_name = update.message.text.strip()
        user_id = update.effective_user.id
        db.create_group(group_name, user_id)
        await update.message.reply_text(f"✅ **{group_name}** guruhi ochildi!", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    except Exception as e:
        await update.message.reply_text(f"⚠️ Xatolik: `{e}`", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def start_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["target_group_id"] = gid

    text = (
        "✍️ **Darslarni kiriting formatda:**\n"
        "```\n"
        "Dars Nomi\n"
        "Ustoz\n"
        "Link (agar yo'q bo'lsa '-')\n"
        "YYYY-MM-DD HH:MM\n"
        "```\n"
        "Darslar ko'p bo'lsa orasiga **`---`** qo'ying."
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard)
    return WAIT_BULK_LESSONS

async def handle_group_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    if message.chat.type not in ["group", "supergroup"]:
        return

    text = message.text.strip()
    if text.startswith("/link_"):
        try:
            token = text.split("_")[1]
            tg_chat_id = str(message.chat.id)
            group = db.get_group_by_secret_token(token)
            
            if not group:
                await message.reply_text("❌ Xatolik: Guruh topilmadi.", parse_mode=ParseMode.MARKDOWN)
                return

            db.link_telegram_group(group["id"], tg_chat_id)
            await message.reply_text(f"✅ **Muvaffaqiyatli ulandi!**", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await message.reply_text(f"❌ Xatolik: `{e}`", parse_mode=ParseMode.MARKDOWN)

async def process_bulk_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    gid = context.user_data.get("target_group_id")
    blocks = raw_text.split("---")
    added_count = 0

    for block in blocks:
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if len(lines) >= 4:
            title, teacher, link, date_str = lines[0], lines[1], lines[2], lines[3]
            meeting_link = "" if link == "-" else link
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                start_iso = dt.strftime("%Y-%m-%d %H:%M:00")
                db.add_lesson(group_id=gid, title=title, teacher=teacher, meeting_link=meeting_link, start_time_iso=start_iso)
                added_count += 1
            except ValueError:
                pass

    await update.message.reply_text(f"✅ Jami **{added_count}** ta dars qo'shildi!", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def show_student_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_subscribed_groups(user.id)

    if not groups:
        await update.message.reply_text("Siz hech qaysi guruhga a'zo emassiz.", reply_markup=main_menu_keyboard())
        return

    for g in groups:
        lessons = db.get_upcoming_lessons_for_group(g["id"])
        if not lessons:
            continue
        
        text = f"📚 **Guruh: {g['name']}**\n\n"
        for idx, l in enumerate(lessons, start=1):
            dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
            text += f"**{idx}. {l['title']}**\n👤 Ustoz: {l['teacher']}\n📅 Vaqti: {dt_naive.strftime('%d.%m.%Y %H:%M')}\n\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Kalendarga saqlash (.ics)", callback_data=f"download_ics_{g['id']}")]
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def show_user_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_subscribed_groups(user.id)

    if not groups:
        await update.message.reply_text("Siz hali guruhga obuna bo'lmagansiz.", reply_markup=main_menu_keyboard())
        return

    keyboard = [[InlineKeyboardButton(f"❌ {g['name']} - Bekor qilish", callback_data=f"unsub_{g['id']}")] for g in groups]
    await update.message.reply_text("📋 **Obunalaringiz:**", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def unsubscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        gid = int(query.data.split("_")[1])
        db.remove_subscriber(query.from_user.id, gid)
        await query.edit_message_text("✅ Obuna bekor qilindi.")
    except Exception:
        pass

async def ics_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        group_id = int(query.data.split("_")[2])
        group = db.get_group(group_id)
        lessons = db.get_upcoming_lessons_for_group(group_id)
        ics_file = generate_ics_calendar(group["name"], lessons)
        await query.message.reply_document(document=ics_file, filename=f"{group['name']}_darslar.ics")
    except Exception as e:
        await query.message.reply_text(f"Xatolik: {e}")

async def show_managed_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_owned_groups(user.id)
    if not groups:
        await update.message.reply_text("Sizda guruhlar yo'q.", reply_markup=main_menu_keyboard())
        return

    keyboard = [[InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"managegroup_{g['id']}")] for g in groups]
    await update.message.reply_text("⚙️ Guruhni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

async def group_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    bot = await context.bot.get_me()

    if data.startswith("managegroup_"):
        gid = int(data.split("_")[1])
        group = db.get_group(gid)
        invite_link = f"https://t.me/{bot.username}?start=g_{group['invite_code']}"
        
        btns = [
            [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{gid}")],
            [InlineKeyboardButton("📋 Darslar Ro'yxati", callback_data=f"listlessons_{gid}")],
            [InlineKeyboardButton("📅 Haftalik jadval", callback_data=f"weeksched_{gid}")],
            [InlineKeyboardButton("📚 Fanlar", callback_data=f"curriculum_{gid}")],
            [InlineKeyboardButton("👥 A'zolar", callback_data=f"groupmembers_{gid}")],
            [InlineKeyboardButton("🗑 O'chirish", callback_data=f"confirmdel_{gid}")]
        ]
        await query.edit_message_text(f"📌 **{group['name']}**\n🔗 `{invite_link}`", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))
    elif data.startswith("confirmdel_"):
        gid = int(data.split("_")[1])
        btns = [[InlineKeyboardButton("Ha", callback_data=f"delgroup_{gid}"), InlineKeyboardButton("Yo'q", callback_data=f"managegroup_{gid}")]]
        await query.edit_message_text("O'chirilsinmi?", reply_markup=InlineKeyboardMarkup(btns))
    elif data.startswith("delgroup_"):
        db.delete_group(int(data.split("_")[1]))
        await query.edit_message_text("🗑 O'chirildi.")

async def group_members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subs = db.get_subscribers(int(query.data.split("_")[1]))
    await query.message.reply_text(f"Jami a'zolar: {len(subs)} ta")

async def list_lessons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lessons = db.get_upcoming_lessons_for_group(int(query.data.split("_")[1]))
    for l in lessons:
        await query.message.reply_text(f"📖 {l['title']} - {l['start_time']}")

async def delete_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db.delete_lesson(int(query.data.split("_")[1]))
    await query.edit_message_text("🗑 O'chirildi.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return
    u, g, l = db.get_total_stats()
    await update.message.reply_text(f"👑 Admin Panel\nFoydalanuvchilar: {u}, Guruhlar: {g}, Darslar: {l}")

async def admin_kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID or not context.args:
        return
    db.delete_user_from_bot(int(context.args[0]))
    await update.message.reply_text("✅ O'chirildi.")

async def show_weekly_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    keyboard = [[InlineKeyboardButton(f"📅 Kun {i}", callback_data=f"editday_{gid}_{i}")] for i in range(6)]
    await query.edit_message_text("Haftalik jadval:", reply_markup=InlineKeyboardMarkup(keyboard))

async def edit_day_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    context.user_data["sched_gid"], context.user_data["sched_day"] = int(parts[1]), int(parts[2])
    await query.message.reply_text("Jadval matnini yuboring:", reply_markup=cancel_keyboard)
    return WAIT_DAY_SCHEDULE

async def save_day_schedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.save_day_schedule(context.user_data.get("sched_gid"), context.user_data.get("sched_day"), update.message.text.strip())
    await update.message.reply_text("✅ Saqlandi!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def show_curriculum_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    items = db.get_all_curriculum(gid)
    text = "\n".join([f"{i['subject_title']} ({i['total_count']})" for i in items]) if items else "Bo'sh"
    keyboard = [[InlineKeyboardButton("➕ Fan qo'shish", callback_data=f"addcurr_{gid}")]], [[InlineKeyboardButton("Orqaga", callback_data=f"managegroup_{gid}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_add_curriculum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["curr_gid"] = int(query.data.split("_")[1])
    await query.message.reply_text("Fan va sonini kiriting (Fan | 30):", reply_markup=cancel_keyboard)
    return WAIT_CURRICULUM_ITEM

async def save_curriculum_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split("|")
    db.add_curriculum_item(context.user_data.get("curr_gid"), parts[0].strip(), int(parts[1].strip()))
    await update.message.reply_text("✅ Qo'shildi!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def send_daily_schedule_job(context: ContextTypes.DEFAULT_TYPE):
    pass

# --- Main App ---
def main():
    db.init_db()
    db.cleanup_expired_data()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.job_queue.run_repeating(check_reminders, interval=60, first=5)
    app.job_queue.run_daily(
        send_daily_schedule_job, 
        time=datetime.strptime("12:50", "%H:%M").time(), 
        days=(0, 1, 2, 3, 4, 5),
        tz=TZ
    )
    
    create_group_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_CREATE_GROUP}$"), start_create_group)],
        states={WAIT_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.Regex(f"^{BTN_BACK}$"), save_group_name)]},
        fallbacks=[MessageHandler(filters.Regex(f"^{BTN_BACK}$"), cancel_group_creation)],
        per_message=False
    )

    add_lesson_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_lesson, pattern="^addlesson_")],
        states={WAIT_BULK_LESSONS: [MessageHandler(filters.TEXT & ~filters.Regex(f"^{BTN_BACK}$"), process_bulk_lessons)]},
        fallbacks=[MessageHandler(filters.Regex(f"^{BTN_BACK}$"), cancel_group_creation)],
        per_message=False
    )

    day_schedule_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_day_schedule, pattern="^editday_")],
        states={WAIT_DAY_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.Regex(f"^{BTN_BACK}$"), save_day_schedule_text)]},
        fallbacks=[MessageHandler(filters.Regex(f"^{BTN_BACK}$"), cancel_group_creation)],
        per_message=False
    )
    
    curriculum_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_curriculum, pattern="^addcurr_")],
        states={WAIT_CURRICULUM_ITEM: [MessageHandler(filters.TEXT & ~filters.Regex(f"^{BTN_BACK}$"), save_curriculum_item)]},
        fallbacks=[MessageHandler(filters.Regex(f"^{BTN_BACK}$"), cancel_group_creation)],
        per_message=False
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("kick", admin_kick_user))

    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)
    app.add_handler(day_schedule_conv)
    app.add_handler(curriculum_conv)

    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_LESSONS}$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SUBSCRIPTIONS}$"), show_user_subscriptions))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SETTINGS}$"), show_settings))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CREATE_GROUP}$"), start_create_group))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_linking))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_MANAGE_GROUPS}$"), show_managed_groups))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_GUIDE}$"), show_guide))

    app.add_handler(CallbackQueryHandler(ics_download_callback, pattern="^download_ics_"))
    app.add_handler(CallbackQueryHandler(group_members_callback, pattern="^groupmembers_"))
    app.add_handler(CallbackQueryHandler(unsubscribe_callback, pattern="^unsub_"))
    app.add_handler(CallbackQueryHandler(toggle_setting_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^(delete_lesson_|dellesson_)"))
    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_|linkgroup_|unlinkgroup_|confirmdel_)"))
    app.add_handler(CallbackQueryHandler(show_weekly_schedule_menu, pattern="^weeksched_"))
    app.add_handler(CallbackQueryHandler(edit_day_schedule, pattern="^editday_"))
    app.add_handler(CallbackQueryHandler(show_curriculum_menu, pattern="^curriculum_"))
    
    # --- BOTNI ISHGA TUSHIRADIGAN ASOSIY QATOR ---
    app.run_polling()

if __name__ == "__main__":
    main()
