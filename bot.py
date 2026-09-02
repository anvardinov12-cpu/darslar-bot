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
        
        # 1. Vaqtni Toshkent vaqti (TZ) deb belgilaymiz
        dt_local = TZ.localize(dt_naive)
        
        # 2. Xalqaro UTC vaqtiga avtomatik o'giramiz (astimezone)
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

    # Agar xabar guruh yoki superguruhdan yuborilgan bo'lsa, /start buyrug'iga javob bermaymiz
    if message.chat.type in ["group", "supergroup"]:
        return

    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if group:
            db.add_subscriber(user.id, group["id"], user.first_name)
            await message.reply_text(
                f"🎉 Siz **{group['name']}** guruhiga muvaffaqiyatli a'zo bo'ldingiz!\n\n"
                f"Dars eslatmalari darsingizdan 1 kun, 12, 6, 1 soat, 15 daqiqa avval va dars boshlanganida yuboriladi.\n\n"
                f"---\n\n"
                f"📌 **Botdan foydalanish tartibi:**\n"
                f"1️⃣ **Eslatmalar:** Dars vaqti yaqinlashganda bot sizga avtomatik ravishda eslatma va havolalarini yuboradi.\n"
                f"2️⃣ **Sozlamalar:** Eslatma vaqtlarini o'zingizga moslash uchun menyudan foydalaning.\n"
                f"3️⃣ **Guruhdan chiqish:** '📋 Obunalarim' bo'limidan istalgan vaqtda obunangizni bekor qilishingiz mumkin.",
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
    
# --- Guide / Foydalanish tartibi ---
async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **BOTDAN FOYDALANISH YO'RIQNOMASI**\n\n"
        "Botimizdan quyidagi **2 xil yo'nalishda** foydalanishingiz mumkin:\n\n"
        "1️⃣ **Oddiy o'quvchi / Talaba uchun:**\n"
        "• Ustozingiz yoki adminingiz bergan maxsus **havola (link)** ustiga bosing.\n"
        "• Botga kirib guruhga avtomatik a'zo bo'lasiz.\n"
        "• Dars vaqti yaqinlashganda bot sizga eslatma va havolalarini yuborib turadi.\n"
        "• Agar biron guruh eslatmalari kerak bo'lmasa, menyudagi **'📋 Obunalarim'** bo'limiga kirib, o'sha guruhdan obunangizni osongina bekor qilishingiz mumkin.\n\n"
        "2️⃣ **Admin / O'qituvchi uchun:**\n"
        "• Menyudagi **'➕ Yangi Guruh Ochish'** tugmasini bosib o'z dars guruhingizni oching.\n"
        "• **'📂 Guruhlarimni Boshqarish'** bo'limi orqali guruhingizga darslarni qo'shing (ko'p darslarni shablon orqali bir yo'la kiritish mumkin).\n"
        "• Chiqqan **A'zolik havolasini** o'quvchilaringizga ulashing.\n"
        "• O'quvchilar shu havola orqali guruhga qo'shiladi, siz esa ularning ro'yxatini ko'rib, zarur paytda e'lonlar yubora olasiz!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())

# --- Settings ---
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    st = db.get_user_settings(user.id)

    def icon(val): return "✅" if val == 1 else "❌"

    text = "⚙️🔔 **Eslatma Sozlamalari**\n\nQaysi vaqtlarda sizga eslatma kelishini tanlang:"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{icon(st['rem_24h'])} 1 kun (24 soat) oldin", callback_data="toggle_24h")],
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
    
# --- Create Group ---
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
        await update.message.reply_text(f"✅ **{group_name}** guruhi ochildi!\n\n\"Guruhlarimni boshqarish\" menyusidan guruhingizga dars qo'shishingiz mumkin", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    except Exception as e:
        await update.message.reply_text(f"⚠️ Xatolik: `{e}`", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- Bulk Add Lessons ---
async def start_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["target_group_id"] = gid

    text = (
        "✍️ **Darslarni kiriting:**\n\n"
        "Darslar qo'shilishi uchun ma'lumotlari quyidagi formatda yozilishi shart. Darslar bir nechta bo'lsa har bir dars orasiga **`---`** qo'ying.\n\n"
        "Format:\n"
        "```\n"
        "Dars Nomi\n"
        "Ustoz\n"
        "Link (agar yo'q bo'lsa '-')\n"
        "YYYY-MM-DD HH:MM\n"
        "```\n\n"
        "Agar moslab yozishda qiyinchilikka uchrasangiz, formatni ko'chirib olib darslaringiz ro'yxati va formatni biror AI chatga yuboring, darslar orasiga `---` qo'yib shu formatga moslab berishini so'rang. 1-2 soniyada formatlab beradi, so'ng tayyor formatni shuyerga yuboring."
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard)
    return WAIT_BULK_LESSONS

# Real Telegram guruhdan turib /link_{secret_token} yuborilganda ishlaydi
async def handle_group_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
        
    # Faqat guruh yoki superguruhlarda ishlashi uchun
    if message.chat.type not in ["group", "supergroup"]:
        return

    text = message.text.strip()
    if text.startswith("/link_"):
        try:
            token = text.split("_")[1] # Maxfiy tokenni ajratib olamiz
            tg_chat_id = str(message.chat.id)
            
            # Token bo'yicha guruhni bazadan qidiramiz
            group = db.get_group_by_secret_token(token)
            
            if not group:
                await message.reply_text("❌ Xatolik: Bunday maxfiy kalitli guruh topilmadi yoki havola eskirgan.", parse_mode=ParseMode.MARKDOWN)
                return

            group_id = group["id"]
            
            # Bazaga chat_id ni saqlaymiz
            db.link_telegram_group(group_id, tg_chat_id)
            
            await message.reply_text(
                f"✅ **Muvaffaqiyatli ulandi!**\n\n"
                f"Bu Telegram guruh 'Darslar Eslatma bot'dagi **\"{group['name']}\"** guruhining jadvaliga muvaffaqiyatli ulandi! "
                f"Endi dars vaqti yaqinlashganda va kelganda eslatmalar shu yerga keladi.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            await message.reply_text(f"❌ Xatolik yuz berdi: `{e}`", parse_mode=ParseMode.MARKDOWN)

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

# --- Display Lessons ---
async def show_student_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_subscribed_groups(user.id)

    if not groups:
        await update.message.reply_text("Siz hech qaysi guruhga a'zo emassiz.", reply_markup=main_menu_keyboard())
        return

    has_lessons = False
    for g in groups:
        lessons = db.get_upcoming_lessons_for_group(g["id"])
        if not lessons:
            continue
        
        has_lessons = True
        text = f"📚 **Guruh: {g['name']}**\n\n"
        for idx, l in enumerate(lessons, start=1):
            dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
            text += f"**{idx}. {l['title']}**\n👤 Ustoz: {l['teacher']}\n📅 Vaqti: {dt_naive.strftime('%d.%m.%Y %H:%M')}\n\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Barcha darslarni kalendarga saqlash (.ics)", callback_data=f"download_ics_{g['id']}")]
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    if not has_lessons:
        await update.message.reply_text("Yaqin orada rejalashtirilgan darslar yo'q.", reply_markup=main_menu_keyboard())

# --- Subscriptions Management (Obunalarim) ---
async def show_user_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_subscribed_groups(user.id)

    if not groups:
        await update.message.reply_text("Siz hali hech qanday guruhga obuna bo'lmagansiz.", reply_markup=main_menu_keyboard())
        return

    text = "📋 **Sizning obunalaringiz:**\n\nQuyidagi guruhlardan birortasining eslatmalarini to'xtatish uchun obunani bekor qilishingiz mumkin:"
    keyboard = []
    for g in groups:
        keyboard.append([InlineKeyboardButton(f"❌ {g['name']} - Obunani bekor qilish", callback_data=f"unsub_{g['id']}")])

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def unsubscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # Tugma aylanishini to'xtatish uchun darhol javob beramiz
    try:
        await query.answer("Obuna bekor qilinmoqda...")
    except Exception:
        pass
    
    try:
        data_parts = query.data.split("_")
        if len(data_parts) < 2:
            return
            
        gid = int(data_parts[1])
        user_id = query.from_user.id
        
        # 1. Bazadan obunani o'chiramiz
        db.remove_subscriber(user_id, gid)
        
        # 2. Foydalanuvchining qolgan obunalarini tekshiramiz
        groups = db.get_user_subscribed_groups(user_id)
        if not groups:
            await query.edit_message_text("✅ Obuna muvaffaqiyatli bekor qilindi.\n\nSizda hozircha faol obunalar yo'q.")
            return

        # 3. Qolgan guruhlar uchun tugmalarni qaytadan chizamiz
        keyboard = []
        for g in groups:
            keyboard.append([InlineKeyboardButton(f"❌ {g['name']} - Obunani bekor qilish", callback_data=f"unsub_{g['id']}")])

        await query.edit_message_text(
            "📋 **Sizning obunalaringiz:**\n\nQuyidagi guruhlardan birortasining eslatmalarini to'xtatish uchun obunani bekor qilishingiz mumkin:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Unsubscribe xatoligi: {e}")
        try:
            await query.message.reply_text("✅ Obuna bekor qilindi.")
        except Exception:
            pass
        
async def ics_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ .ics fayli tayyorlanmoqda...")

    try:
        group_id = int(query.data.split("_")[2])
        group = db.get_group(group_id)
        lessons = db.get_upcoming_lessons_for_group(group_id)

        if not lessons:
            await query.message.reply_text("❌ Ushbu guruhda darslar topilmadi.")
            return

        ics_file = generate_ics_calendar(group["name"], lessons)

        await query.message.reply_document(
            document=ics_file,
            filename=f"{group['name']}_darslar.ics",
            caption=f"📅 **{group['name']}** guruhining darslar kalendari fayli.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await query.message.reply_text(f"⚠️ Faylni yuklashda xatolik: {e}")

# --- Group Management ---
async def show_managed_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = db.get_user_owned_groups(user.id)

    if not groups:
        await update.message.reply_text("Sizda hali yaratilgan guruhlar yo'q.", reply_markup=main_menu_keyboard())
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

        # Guruhda chat_id bormi-yo'qmi aniqlaymiz (xatolik bermasligi uchun try ishlatamiz)
        try:
            chat_id = group['chat_id']
        except Exception:
            chat_id = None
        
        if chat_id:
            try:
                # Bot ID orqali real guruh nomini oladi
                chat_info = await context.bot.get_chat(chat_id)
                status_text = f"✅ Ulangan telegram guruh: **{chat_info.title}**"
            except Exception:
                # Agar bot guruhdan chiqarib yuborilgan bo'lsa yoki ismini ololmasa:
                status_text = f"✅ Ulangan telegram guruh ID: `{chat_id}` (bot guruhda yo'q)"
        else:
            status_text = "❌ Hali telegram guruhga ulanmagan"
        
        # STATUS TEXT MATN ICHIGA QO'SHILDI
        text = f"📌 **Guruh:** {group['name']}\n{status_text}\n🔗 **A'zolik havolasi:** `{invite_link}`"
        
        btns = [
            [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{gid}")],
            [InlineKeyboardButton("📋 Darslar Ro'yxati", callback_data=f"listlessons_{gid}")],
            [InlineKeyboardButton("📅 Haftalik darslar jadvali", callback_data=f"weeksched_{gid}")],
            [InlineKeyboardButton("📚 Barcha darslar adadi va ro'yxati", callback_data=f"curriculum_{gid}")],
            [InlineKeyboardButton("👥 Guruh A'zolari", callback_data=f"groupmembers_{gid}")],
            [InlineKeyboardButton("📢 Guruhga E'lon Yuborish", callback_data=f"announcegroup_{gid}")],
        ]
        
        # TUGMALAR SHARTGA KO'RA QO'SHILADI:
        if chat_id:
            # Agar ulangan bo'lsa, faqat "Uzish" tugmasi chiqadi
            btns.append([InlineKeyboardButton("❌ Telegram Guruhni Uzish", callback_data=f"unlinkgroup_{gid}")])
        else:
            # Agar ulanmagan bo'lsa, faqat "Ulash" tugmasi chiqadi
            btns.append([InlineKeyboardButton("🔗 Guruhni Telegram Guruhga Ulash", callback_data=f"linkgroup_{gid}")])
            
        btns.append([InlineKeyboardButton("🗑 Guruhni O'chirish", callback_data=f"confirmdel_{gid}")])
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("confirmdel_"):
        gid = int(data.split("_")[1])
        text = "⚠️ **Diqqat!**\n\nHaqiqatan ham bu guruhni va unga tegishli barcha darslarni o'chirib tashlamoqchimisiz?\n_Bu amalni ortga qaytarib bo'lmaydi!_"
        
        btns = [
            [InlineKeyboardButton("🗑 Ha, o'chirish", callback_data=f"delgroup_{gid}")],
            [InlineKeyboardButton("⬅️ Bekor qilish", callback_data=f"managegroup_{gid}")]
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))
        
    elif data.startswith("delgroup_"):
        gid = int(data.split("_")[1])
        db.delete_group(gid)
        await query.edit_message_text("🗑 Guruh va undagi barcha darslar muvaffaqiyatli o'chirildi.")
    
    elif data.startswith("linkgroup_"):
        await query.answer()
        try:
            gid = int(data.split("_")[1])
            group = db.get_group(gid)
            
            # Agar guruhda token hali bo'lmasa (eski guruhlar uchun), uni yaratib qo'yamiz
            token = group['secret_token'] if 'secret_token' in group.keys() and group['secret_token'] else None
            if not token:
                import secrets
                token = secrets.token_hex(6)
                with db.get_db() as conn:
                    conn.execute("UPDATE groups SET secret_token = ? WHERE id = ?", (token, gid))
        
            text = (
                f"🔗 Eslatuvchi botni Telegram guruhga ulash uchun yo'riqnoma:\n\n"
                f"1️⃣ Botimizni dars o'tadigan real Telegram guruhingizga qo'shing va **Administrator** huquqini bering.\n"
                f"2️⃣ O'sha Telegram guruh ichiga kiring va ushbu linkni yuboring:\n\n"
                f"👉 `/link_{token}`\n\n"
                f"Shundan so'ng bot avtomatik ravishda ushbu guruhni xavfsiz bog'lab oladi!"
            )
            back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=f"managegroup_{gid}")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_btn)
        except Exception as e:
            await query.message.reply_text(f"Xatolik: {e}")
    
    elif data.startswith("unlinkgroup_"):
        gid = int(data.split("_")[1])
        
        # 1. Bazadan guruhni uzamiz
        db.unlink_telegram_group(gid)
        
        # 2. Ekranda qisqa popup (qalqib chiquvchi) xabar ko'rsatamiz
        await query.answer("✅ Telegram guruh muvaffaqiyatli uzildi!", show_alert=False)
        
        # 3. Menyuni "Ulanmagan" holatiga o'tkazib, xuddi shu xabarning o'zini yangilaymiz
        group = db.get_group(gid)
        invite_link = f"https://t.me/{bot.username}?start=g_{group['invite_code']}"
        text = f"📌 **Guruh:** {group['name']}\n❌ Hali telegram guruhga ulanmagan\n🔗 **A'zolik havolasi:** `{invite_link}`"
        
        btns = [
            [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{gid}")],
            [InlineKeyboardButton("📋 Darslar Ro'yxati", callback_data=f"listlessons_{gid}")],
            [InlineKeyboardButton("👥 Guruh A'zolari", callback_data=f"groupmembers_{gid}")],
            [InlineKeyboardButton("📢 Guruhga E'lon Yuborish", callback_data=f"announcegroup_{gid}")],
            [InlineKeyboardButton("🔗 Guruhni Telegram Guruhga Ulash", callback_data=f"linkgroup_{gid}")],
            [InlineKeyboardButton("🗑 Guruhni O'chirish", callback_data=f"confirmdel_{gid}")]
        ]
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

# --- Guruh a'zolarini ism bilan ko'rsatish ---
async def group_members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Ro'yxat olinmoqda...")
    gid = int(query.data.split("_")[1])
    group = db.get_group(gid)
    subs = db.get_subscribers(gid)

    if not subs:
        # Bu yerda ham HTML ga o'tkazdik
        await query.message.reply_text(f"📉 <b>{group['name']}</b> guruhida hali a'zolar yo'q.", parse_mode=ParseMode.HTML)
        return

    # Sarlavhani tayyorlab olamiz
    header = f"👥 <b>{group['name']}</b> guruhi a'zolari ({len(subs)} ta):\n\n"
    text = header

    for idx, user_info in enumerate(subs, start=1):
        uid = user_info["user_id"]
        name = user_info["full_name"]
        if not name:
            name = "Foydalanuvchi"
            
        safe_name = html.escape(name)
        # \u200E belgisi matn yo'nalishini va tartibini to'g'ri saqlaydi
        line = f"\u200E{idx}. 👤 <a href='tg://user?id={uid}'>{safe_name}</a> (ID: <code>{uid}</code>)\n"

        # Agar matn 4000 belgidan oshib ketsa, oldingi qismni yuborib, 
        # yangi xabarni sarlavhadan boshlab yig'amiz (teglar kesilmaydi)
        if len(text) + len(line) > 4000:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML)
            text = header

        text += line

    # Qolgan oxirgi qismni yuboramiz
    if text:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)

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

# --- GROUP ANNOUNCEMENT ---
async def start_group_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["announce_gid"] = gid

    group = db.get_group(gid)
    await query.message.reply_text(
        f"📢 **{group['name']}** guruhi a'zolariga yuboriladigan e'lon matnini kiriting:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard
    )
    return GROUP_ANNOUNCE_WAIT_MSG

async def send_group_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    gid = context.user_data.get("announce_gid")
    
    group = db.get_group(gid)
    if not group:
        await msg.reply_text("❌ Guruh topilmadi.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    subscribers = db.get_subscribers(gid)
    if not subscribers and not group.get('chat_id'):
        await msg.reply_text("❌ Ushbu guruhda na a'zolar va na ulangan Telegram guruh bor.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    sent_count, failed_count = 0, 0
    announce_text = f"📢 **E'LON [{group['name']}]**\n\n{msg.text}"

    # 1. Shaxsiy chatlarga yuborish
    if subscribers:
        for u_info in subscribers:
            u_id = u_info["user_id"]
            try:
                await context.bot.send_message(chat_id=u_id, text=announce_text, parse_mode=ParseMode.MARKDOWN)
                sent_count += 1
            except Exception:
                failed_count += 1

    # 2. Ulangan real Telegram guruhga yuborish
    group_sent = False
    chat_id = group['chat_id'] if 'chat_id' in group.keys() else None
    
    if chat_id:
        try:
            await context.bot.send_message(chat_id=chat_id, text=announce_text, parse_mode=ParseMode.MARKDOWN)
            group_sent = True
        except Exception as e:
            print(f"Real guruhga e'lon yuborishda xatolik: {e}")

    # 3. Adminga yakuniy hisobotni chiqarish
    report_text = f"✅ **E'lon yuborildi!**\n\n"
    report_text += f"📥 Obunachilarga: **{sent_count}** ta\n"
    report_text += f"❌ Yetib bormadi: **{failed_count}** ta"
    
    if chat_id:
        status_g = "Muvaffaqiyatli 🟢" if group_sent else "Yuborib bo'lmadi 🔴 (Bot guruhda yo'q yoki huquqi yo'q)"
        report_text += f"\n👥 Ulangan Telegram guruhga: {status_g}"

    await msg.reply_text(report_text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
    return ConversationHandler.END
    
# --- SUPER ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    # Guruh yoki superguruhdan yozilsa, umuman javob bermaymiz
    if message.chat.type in ["group", "supergroup"]:
        return

    user = update.effective_user
    if user.id != SUPER_ADMIN_ID:
        await message.reply_text("⛔️ Ushbu bo'lim faqat Bosh Admin uchun!")
        return

    total_users, total_groups, total_lessons = db.get_total_stats()
    text = (
        "👑 **SUPER ADMIN PANEL**\n\n"
        f"📊 **Statistika:**\n"
        f"• Barcha obunachilar: **{total_users} ta**\n"
        f"• Jami guruhlar: **{total_groups} ta**\n"
        f"• Faol darslar: **{total_lessons} ta**\n\n"
        f"⚠️ *Foydalanuvchini o'chirish (ban)* uchun botga:\n`/kick ID_RAQAM` deb yozing."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Barcha Obunachilar", callback_data="get_all_subscribers"),
         InlineKeyboardButton("📁 Joriy Guruhlar", callback_data="admin_all_groups")],
        [InlineKeyboardButton("📚 Joriy Darslar", callback_data="admin_all_lessons"),
         InlineKeyboardButton("📢 Xabar tarqatish", callback_data="admin_broadcast")]
    ])
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Ro'yxat olinmoqda...")

    if query.from_user.id != SUPER_ADMIN_ID:
        return

    users_list = db.get_all_users_list()
    if not users_list:
        await query.message.reply_text("Obunachilar topilmadi.")
        return

async def admin_all_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Guruhlar ro'yxati olinmoqda...")
    if query.from_user.id != SUPER_ADMIN_ID:
        return

    groups = db.get_all_groups_with_owners()
    if not groups:
        await query.message.reply_text("Hozircha bazada guruhlar yo'q.")
        return

    header = f"📁 <b>Barcha Guruhlar Ro'yxati ({len(groups)} ta):</b>\n\n"
    text = header
    for idx, g in enumerate(groups, start=1):
        owner_name = html.escape(g["owner_name"])
        g_name = html.escape(g["name"])
        line = f"\u200E{idx}. <b>{g_name}</b> (ID: {g['id']})\n   👤 Egasi: <a href='tg://user?id={g['owner_id']}'>{owner_name}</a> (ID: <code>{g['owner_id']}</code>)\n\n"

        if len(text) + len(line) > 4000:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML)
            text = header
        text += line

    if text:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)

async def admin_all_lessons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Darslar ro'yxati olinmoqda...")
    if query.from_user.id != SUPER_ADMIN_ID:
        return

    lessons = db.get_all_lessons_with_groups()
    if not lessons:
        await query.message.reply_text("Hozircha faol darslar mavjud emas.")
        return

    header = f"📚 <b>Barcha Kelgusi Darslar ({len(lessons)} ta):</b>\n\n"
    text = header
    for idx, l in enumerate(lessons, start=1):
        dt = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
        g_name = html.escape(l["group_name"])
        l_title = html.escape(l["title"])
        teacher = html.escape(l['teacher']) if l['teacher'] else "Ko'rsatilmagan"
        
        line = f"\u200E{idx}. 📖 <b>{l_title}</b>\n   📁 Guruh: {g_name}\n   👤 Ustoz: {teacher}\n   🗓 Vaqti: {dt.strftime('%d.%m.%Y %H:%M')}\n\n"

        if len(text) + len(line) > 4000:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML)
            text = header
        text += line

    if text:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    # Sarlavhadan boshlaymiz
    header = f"👥 <b>Barcha Bot Obunachilari ({len(users_list)} ta):</b>\n\n"
    text = header
    
    for idx, u in enumerate(users_list, start=1):
        uid = u["user_id"]
        name = u["full_name"]
        if not name:
            name = "Foydalanuvchi"
            
        safe_name = html.escape(name)
        line = f"\u200E{idx}. 👤 <a href='tg://user?id={uid}'>{safe_name}</a> (ID: <code>{uid}</code>)\n"

        # Agar yangi qatorni qo'shganda matn 4000 belgidan oshib ketsa,
        # oldingi qismni yuborib, yangi xabar yig'ishni boshlaymiz (teglarni kesib yubormaslik uchun)
        if len(text) + len(line) > 4000:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML)
            text = header  # Yangi xabarga ham sarlavhani qo'yamiz
            
        text += line

    # Qolgan oxirgi qismni yuboramiz
    if text:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)

async def admin_kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Foydalanish: `/kick 123456789` (Foydalanuvchi ID sini yozing)", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        uid = int(context.args[0])
        db.delete_user_from_bot(uid)
        await update.message.reply_text(f"✅ ID: `{uid}` bot bazasidan muvaffaqiyatli o'chirildi va guruhlardan chiqarildi.", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID kiritildi. Faqat raqam kiriting.")

# --- BROADCAST ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return ConversationHandler.END

    msg_text = "📢 **Barcha foydalanuvchilarga xabar tarqatish**\n\nMatnni kiriting:"
    if update.callback_query:
        await update.callback_query.message.reply_text(msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard)
    else:
        await update.message.reply_text(msg_text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard)

    return BROADCAST_WAIT_MSG

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    users_list = db.get_all_users_list()

    sent_count, failed_count = 0, 0
    for u in users_list:
        u_id = u["user_id"]
        try:
            await msg.copy(chat_id=u_id)
            sent_count += 1
        except Exception:
            failed_count += 1

    await msg.reply_text(
        f"✅ **Xabar tarqatildi!**\n\n📥 Muvaffaqiyatli: **{sent_count}**\n❌ Yetib bormadi: **{failed_count}**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# --- YANGI: Haftalik jadval va Darslar ro'yxatini boshqarish funksiyalari ---

DAYS_OF_WEEK = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

async def show_weekly_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    
    keyboard = []
    for idx, day_name in enumerate(DAYS_OF_WEEK):
        keyboard.append([InlineKeyboardButton(f"📅  {day_name}", callback_data=f"editday_{gid}_{idx})".replace(")", ""))])
    
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=f"managegroup_{gid}")])
    await query.edit_message_text(
        "📅 **Haftalik darslar jadvali**\n\nKunni tanlang va shu kun uchun darslar ro'yxatini tahrirlang:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def edit_day_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    gid, day_idx = int(parts[1]), int(parts[2])
    
    context.user_data["sched_gid"] = gid
    context.user_data["sched_day"] = day_idx
    
    current_text = db.get_day_schedule(gid, day_idx)
    day_name = DAYS_OF_WEEK[day_idx]
    
    text = (
        f"📌 **{day_name} kuni uchun darslar:**\n\n"
        f"Hozirgi ro'yxat:\n{current_text if current_text else '_Hali kiritilmagan_'}\n\n"
        "✍️ Ushbu kun uchun fanlar ro'yxatini bitta qilib yuboring, u yangilanadi  (Fan Umumiy darslar ro'yxatida bo'lishi kerak!)  masalan: `1. Iqtisodiyot\n2. Huquqshunoslik\n3. Matematika`"
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard)
    return WAIT_DAY_SCHEDULE

async def save_day_schedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    gid = context.user_data.get("sched_gid")
    day_idx = context.user_data.get("sched_day")
    
    # 1. Guruhning umumiy fanlar ro'yxatini olamiz
    curriculum_items = db.get_all_curriculum(gid)
    if not curriculum_items:
        await update.message.reply_text(
            "❌ Avval 'Barcha darslar adadi va ro'yxati' bo'limidan fanlarni va sonini kiritishingiz kerak!",
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END

    # Umumiy ro'yxatdagi fan nomlarini kichik harflarda to'plab olamiz
    valid_subjects = {item["subject_title"].strip().lower(): item for item in curriculum_items}
    
    lines = text.split("\n")
    validated_lines = []
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Raqam va nuqtani ajratib olamiz (masalan: "1. Aqiyda" -> "Aqiyda")
        parts = line_clean.split(".", 1)
        subject_name = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        
        # Agar foydalanuvchi "- 1-dars" deb yozgan bo'lsa ham, asosiy nomni ajratib olamiz
        subject_name = subject_name.split("-")[0].strip()
        
        # 2. Umumiy ro'yxatda bor-yo'qligini tekshiramiz
        if subject_name.lower() in valid_subjects:
            # Toza va tartibli holatda saqlaymiz (masalan: "1. Aqiyda")
            matched_item = valid_subjects[subject_name.lower()]
            formatted_line = f"{len(validated_lines) + 1}. {matched_item['subject_title']}"
            validated_lines.append(formatted_line)
        else:
            await update.message.reply_text(
                f"❌ Xatolik: **'{subject_name}'** fani umumiy darslar ro'yxatida mavjud emas!\n\n"
                f"Iltimos, avval 'Barcha darslar adadi va ro'yxati' bo'limiga shu fanni qo'shing yoki to'g'ri nom yozing.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=cancel_keyboard
            )
            return WAIT_DAY_SCHEDULE

    # Barcha qatorlar tekshiruvdan o'tdi, bazaga saqlaymiz
    final_text = "\n".join(validated_lines)
    db.save_day_schedule(gid, day_idx, final_text)
    
    await update.message.reply_text(
        "✅ Haftalik dars jadvali umumiy ro'yxat bilan solishtirilib, muvaffaqiyatli saqlandi!", 
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# Barcha darslar adadi (Curriculum)
async def show_curriculum_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["curr_gid"] = gid
    
    items = db.get_all_curriculum(gid)
    text = "📚 **Guruhdagi fanlar va umumiy darslar adadi:**\n\n"
    keyboard = []
    
    if items:
        for idx, item in enumerate(items, start=1):
            text += f"{idx}. **{item['subject_title']}** — Jami: {item['total_count']} ta\n"
            keyboard.append([InlineKeyboardButton(f"❌ O'chirish: {item['subject_title']}", callback_data=f"delcurr_{item['id']}_{gid}")])
    else:
        text += "_Hali fanlar kiritilmagan._\n"
        
    keyboard.append([InlineKeyboardButton("➕ Fan qo'shish", callback_data=f"addcurr_{gid}")])
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=f"managegroup_{gid}")])
    
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_add_curriculum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split("_")[1])
    context.user_data["curr_gid"] = gid
    
    await query.message.reply_text(
        "📝 Yangi fan va uning jami dars sonini quyidagi formatda kiriting:\n\n`Fan nomi | Jami dars soni`\n_Misol: Dasturlash | 60_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard
    )
    return WAIT_CURRICULUM_ITEM

async def save_curriculum_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    gid = context.user_data.get("curr_gid")
    
    lines = text.split("\n")
    added_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        for sep in ["-", "|", ":"]:
            if sep in line:
                parts = line.split(sep, 1)
                break
        else:
            await update.message.reply_text(
                f"❌ Xatolik formatda! Qaytadan urinib ko'ring: `{line}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=cancel_keyboard
            )
            return WAIT_CURRICULUM
            
        title = parts[0].strip()
        total_str = parts[1].strip()
        
        if not total_str.isdigit():
            await update.message.reply_text(
                f"❌ Xatolik formatda! Dars soni faqat raqam bo'lishi kerak: `{total_str}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=cancel_keyboard
            )
            return WAIT_CURRICULUM
            
        total = int(total_str)
        db.add_curriculum_item(gid, title, total)
        added_count += 1

    await update.message.reply_text(
        f"✅ Muvaffaqiyatli! Jami {added_count} ta fan ro'yxatga qo'shildi.", 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def delete_curriculum_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    item_id, gid = int(parts[1]), int(parts[2])
    
    db.delete_curriculum_item(item_id)
    # Menyuni qaytadan chaqiramiz
    query.data = f"curriculum_{gid}"
    await show_curriculum_menu(update, context)

async def send_daily_schedule_job(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni ertalab kunlik darslar jadvalini yuboradi va qolgan darslar sonini kamaytirib boradi"""
    now = datetime.now(TZ)
    day_idx = now.weekday()
    
    if day_idx > 5: # Yakshanba bo'lsa yubormaymiz
        return
        
    with db.get_db() as conn:
        groups = conn.execute("SELECT * FROM groups WHERE chat_id IS NOT NULL").fetchall()
        
    for g in groups:
        gid = g["id"]
        chat_id = g["chat_id"]
        schedule_text = db.get_day_schedule(gid, day_idx)
        
        if not schedule_text:
            continue
            
        curriculum_items = db.get_all_curriculum(gid)
        curr_dict = {item["subject_title"].strip().lower(): item for item in curriculum_items}
        
        lines = schedule_text.split("\n")
        active_lessons_lines = []
        valid_counter = 1
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(".", 1)
            subj_name = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            subj_name_lower = subj_name.lower()
            
            if subj_name_lower in curr_dict:
                item = curr_dict[subj_name_lower]
                remaining = item["current_index"] # Qolgan darslar soni
                total = item["total_count"]
                
                if remaining > 0:
                    active_lessons_lines.append(f"{valid_counter}. {item['subject_title']} (Qolgan: {remaining} ta / Jami: {total})")
                    valid_counter += 1
                    
                    # 🔴 ENG MUHIM O'ZGARISH: Har safar dars chiqqanda qolgan darslar sonini 1 taga kamaytiramiz
                    db.update_curriculum_index(item["id"], remaining - 1)
            else:
                active_lessons_lines.append(f"{valid_counter}. {subj_name}")
                valid_counter += 1
                
        if active_lessons_lines:
            final_schedule_text = "\n".join(active_lessons_lines)
            date_str = now.strftime("%d-%B, %Y")
            msg = (
                f"📅 **Bugungi darslar rejasi ({date_str}):**\n\n"
                f"{final_schedule_text}\n\n"
                f"_Talabalar uchun eslatma: Darslarni o'z vaqtida o'zlashtirib boring!_"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logging.error(f"Kunlik jadvalni yuborishda xatolik ({chat_id}): {e}")
                
# --- Main App ---
def main():
    db.init_db()  # <-- MANA SHU QATORNI QO'SHISH SHART!
    db.cleanup_expired_data()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.job_queue.run_repeating(check_reminders, interval=60, first=5)
    app.job_queue.run_daily(send_daily_schedule_job, time=datetime.strptime("19:20", "%H:%M").time(), days=(0,1,2,3,4,5))
    
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

    group_announce_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_group_announce, pattern="^announcegroup_")],
        states={GROUP_ANNOUNCE_WAIT_MSG: [MessageHandler(filters.TEXT & ~filters.Regex(f"^{BTN_BACK}$"), send_group_announce)]},
        fallbacks=[MessageHandler(filters.Regex(f"^{BTN_BACK}$"), cancel_group_creation)],
        per_message=False
    )

    broadcast_conv = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", start_broadcast),
            CallbackQueryHandler(start_broadcast, pattern="^admin_broadcast$")
        ],
        states={BROADCAST_WAIT_MSG: [MessageHandler(filters.ALL & ~filters.Regex(f"^{BTN_BACK}$"), send_broadcast)]},
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

    # Conversation Handlers
    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)
    app.add_handler(group_announce_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(day_schedule_conv)
    app.add_handler(curriculum_conv)

    # Menyu tugmalari
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_LESSONS}$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SUBSCRIPTIONS}$"), show_user_subscriptions)) # <-- MANA BU QATORNI QO'SHING
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SETTINGS}$"), show_settings))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CREATE_GROUP}$"), start_create_group))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_linking))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_MANAGE_GROUPS}$"), show_managed_groups))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_GUIDE}$"), show_guide)) # <-- MANA BU QATORNI HAM QO'SHING

    # Aniq patternli Callback'lar
    app.add_handler(CallbackQueryHandler(admin_all_users_callback, pattern="^get_all_subscribers$"))
    app.add_handler(CallbackQueryHandler(admin_all_groups_callback, pattern="^admin_all_groups$"))
    app.add_handler(CallbackQueryHandler(admin_all_lessons_callback, pattern="^admin_all_lessons$"))
    app.add_handler(CallbackQueryHandler(ics_download_callback, pattern="^download_ics_"))
    app.add_handler(CallbackQueryHandler(group_members_callback, pattern="^groupmembers_"))
    app.add_handler(CallbackQueryHandler(unsubscribe_callback, pattern="^unsub_")) # <-- Obunani bekor qiluvchi handler shu yerda
    
    # Qolgan general Callback Query'lar
    app.add_handler(CallbackQueryHandler(toggle_setting_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^(delete_lesson_|dellesson_)"))
    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_|linkgroup_|unlinkgroup_|confirmdel_)"))
    app.add_handler(CallbackQueryHandler(show_weekly_schedule_menu, pattern="^weeksched_"))
    app.add_handler(CallbackQueryHandler(show_curriculum_menu, pattern="^curriculum_"))
    app.add_handler(CallbackQueryHandler(delete_curriculum_callback, pattern="^delcurr_"))
    
    app.run_polling()

if __name__ == "__main__":
    main()
