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


# --- Background Reminder Checker ---
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    lessons = db.get_all_future_lessons()
    
    for l in lessons:
        lesson_id = l["id"]
        group_id = l["group_id"]
        group = db.get_group(group_id)
        if not group:
            continue
            
        dt_naive = datetime.strptime(l["start_time"], "%Y-%m-%d %H:%M:%S")
        dt_lesson = TZ.localize(dt_naive)
        
        diff_minutes = (dt_lesson - now).total_seconds() / 60.0
        subscribers = db.get_subscribers(group_id)
        
        for sub in subscribers:
            user_id = sub["user_id"]
            if user_id == 0:
                continue
            settings = db.get_user_settings(user_id)
            
            # --- O'ZGARGAN JOYI: include_link parametri qo'shildi ---
            async def send_if_needed(r_type, text_prefix, title_prefix="🔔 **DARS ESLATMASI!**", include_link=False):
                if not db.was_reminder_sent(lesson_id, user_id, r_type):
                    try:
                        # Havola faqat ruxsat berilgan eslatmalarda chiqadi
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
                        logging.error(f"Xabar yuborishda xatolik ({user_id}): {e}")

            if settings.get("rem_24h", 1) == 1 and 1435 <= diff_minutes <= 1445:
                await send_if_needed("24h", "Darsga 24 soat qoldi!", include_link=False)
            elif settings.get("rem_12h", 1) == 1 and 715 <= diff_minutes <= 725:
                await send_if_needed("12h", "Darsga 12 soat qoldi!", include_link=False)
            elif settings.get("rem_6h", 1) == 1 and 355 <= diff_minutes <= 365:
                await send_if_needed("6h", "Darsga 6 soat qoldi!", include_link=False)
            elif settings.get("rem_1h", 1) == 1 and 55 <= diff_minutes <= 65:
                await send_if_needed("1h", "Darsga 1 soat qoldi!", include_link=False)
            elif settings.get("rem_15m", 1) == 1 and 12 <= diff_minutes <= 18:
                # --- 15 daqiqalikda havola chiqadi ---
                await send_if_needed("15m", "Darsga 15 daqiqa qoldi!", include_link=True)
            elif settings.get("rem_now", 1) == 1 and -2 <= diff_minutes <= 3:
                # --- Dars boshlanganda havola chiqadi ---
                await send_if_needed("now", "🔴 Dars boshlandi!", title_prefix="🔴 **DARS BOSHLANDI!**", include_link=True)
                
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
        dt_utc = dt_naive - timedelta(hours=5)
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
BTN_CREATE_GROUP = "➕ Yangi Guruh Yaratish"
BTN_MANAGE_GROUPS = "📂 Guruhlarimni Boshqarish"
BTN_GUIDE = "📖 Foydalanish tartibi"
BTN_BACK = "⬅️ Orqaga"

def main_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_LESSONS), KeyboardButton(BTN_SUBSCRIPTIONS)],
        [KeyboardButton(BTN_SETTINGS), KeyboardButton(BTN_CREATE_GROUP)],
        [KeyboardButton(BTN_MANAGE_GROUPS), KeyboardButton(BTN_GUIDE)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

cancel_keyboard = ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)

# --- Start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("g_"):
        code = args[0][2:]
        group = db.get_group_by_code(code)
        if group:
            db.add_subscriber(user.id, group["id"], user.first_name)
            await update.message.reply_text(
                f"🎉 Siz **{group['name']}** guruhiga muvaffaqiyatli a'zo bo'ldingiz!\n\n"
                f"Dars eslatmalari darsingizdan 1 kun, 12, 6, 1 soat, 15 daqiqa avval va dars boshlanganida yuboriladi.\n\n"
                f"---\n\n"
                f"📌 **Botdan foydalanish tartibi:**\n"
                f"1️⃣ **Eslatmalar:** Dars vaqti yaqinlashganda bot sizga avtomatik ravishda eslatma va Zoom havolalarini yuboradi.\n"
                f"2️⃣ **Sozlamalar:** Eslatma vaqtlarini o'zingizga moslash uchun menyudan foydalaning.\n"
                f"3️⃣ **Guruhdan chiqish:** '📋 Obunalarim' bo'limidan istalgan vaqtda obunangizni bekor qilishingiz mumkin.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard()
            )
            return
        else:
            await update.message.reply_text("❌ Guruh topilmadi yoki havola eskirgan.", reply_markup=main_menu_keyboard())

    db.add_subscriber(user.id, 0, user.first_name)
    await update.message.reply_text(
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
        "• Ustozingiz yoki adminimiz bergan maxsus **havola (link)** ustiga bosing.\n"
        "• Botga kirib guruhga avtomatik a'zo bo'lasiz.\n"
        "• Dars vaqti yaqinlashganda bot sizga eslatma va Zoom havolalarini yuborib turadi.\n"
        "• Agar biron guruh eslatmalari kerak bo'lmasa, menyudagi **'📋 Obunalarim'** bo'limiga kirib, o'sha guruhdan obunangizni osongina bekor qilishingiz mumkin.\n\n"
        "2️⃣ **Admin / O'qituvchi uchun:**\n"
        "• Menyudagi **'➕ Yangi Guruh Yaratish'** tugmasini bosib o'z dars guruhingizni oching.\n"
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
        await update.message.reply_text(f"✅ **{group_name}** guruhi yaratildi!", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())
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
        "Har bir dars orasiga **`---`** qo'ying.\n"
        "Format:\n`Dars Nomi`\n`Ustoz`\n`Zoom Link (-)`\n`YYYY-MM-DD HH:MM`"
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard)
    return WAIT_BULK_LESSONS

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
    # Terminalga yozamiz
    print("--------------------------------------------------")
    print(">>> UNSUBSCRIBE FUNKSIYASIGA KIRDI! <<<")
    print("--------------------------------------------------")
    
    query = update.callback_query
    
    # Telegramga darhol javob beramiz
    try:
        await query.answer("Tekshirildi!", show_alert=True)
    except Exception as e:
        print(f"Answer xatosi: {e}")
        
    # Telegram chatning o'ziga ham xabar yozamiz
    try:
        await query.message.reply_text("✅ Mana, funksiya ishlayapti va chatga yozdi!")
    except Exception as e:
        print(f"Message xatosi: {e}")
        
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
        text = f"📌 **Guruh:** {group['name']}\n🔗 **A'zolik havolasi:** `{invite_link}`"
        btns = [
            [InlineKeyboardButton("👥 Guruh A'zolari", callback_data=f"groupmembers_{gid}")],
            [InlineKeyboardButton("➕ Dars Qo'shish", callback_data=f"addlesson_{gid}")],
            [InlineKeyboardButton("📢 Guruhga E'lon Yuborish", callback_data=f"announcegroup_{gid}")],
            [InlineKeyboardButton("📋 Darslar Ro'yxati", callback_data=f"listlessons_{gid}")],
            [InlineKeyboardButton("🗑 Guruhni O'chirish", callback_data=f"delgroup_{gid}")]
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("delgroup_"):
        gid = int(data.split("_")[1])
        db.delete_group(gid)
        await query.edit_message_text("🗑 Guruh va undagi darslar o'chirildi.")

# --- Guruh a'zolarini ism bilan ko'rsatish ---
async def group_members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Ro'yxat olinmoqda...")
    gid = int(query.data.split("_")[1])
    group = db.get_group(gid)
    subs = db.get_subscribers(gid)

    if not subs:
        await query.message.reply_text(f"📉 **{group['name']}** guruhida hali a'zolar yo'q.", parse_mode=ParseMode.MARKDOWN)
        return

    text = f"👥 **{group['name']}** guruhi a'zolari ({len(subs)} ta):\n\n"
    for idx, user_info in enumerate(subs, start=1):
        uid = user_info["user_id"]
        name = user_info["full_name"]
        text += f"{idx}. 👤 [{name}](tg://user?id={uid}) (ID: `{uid}`)\n"

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await query.message.reply_text(text[x:x+4000], parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

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

    if not subscribers:
        await msg.reply_text("❌ Ushbu guruhda a'zolar yo'q.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    sent_count, failed_count = 0, 0
    announce_text = f"📢 **E'LON [{group['name']}]**\n\n{msg.text}"

    for u_info in subscribers:
        u_id = u_info["user_id"]
        try:
            await context.bot.send_message(chat_id=u_id, text=announce_text, parse_mode=ParseMode.MARKDOWN)
            sent_count += 1
        except Exception:
            failed_count += 1

    await msg.reply_text(
        f"✅ **E'lon yuborildi!**\n\n📥 Yetib bordi: **{sent_count}** ta\n❌ Yetib bormadi: **{failed_count}** ta",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

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
        f"• Faol darslar: **{total_lessons} ta**\n\n"
        f"⚠️ *Foydalanuvchini o'chirish (ban)* uchun botga:\n`/kick ID_RAQAM` deb yozing."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Barcha Obunachilar Ro'yxati", callback_data="get_all_subscribers")],
        [InlineKeyboardButton("📢 Xabar tarqatish", callback_data="admin_broadcast")]
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Ro'yxat olinmoqda...")

    if query.from_user.id != SUPER_ADMIN_ID:
        return

    users_list = db.get_all_users_list()
    if not users_list:
        await query.message.reply_text("Obunachilar topilmadi.")
        return

    text = f"👥 **Barcha Bot Obunachilari ({len(users_list)} ta):**\n\n"
    for idx, u in enumerate(users_list, start=1):
        uid = u["user_id"]
        name = u["full_name"]
        text += f"{idx}. 👤 [{name}](tg://user?id={uid}) (ID: `{uid}`)\n"

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await query.message.reply_text(text[x:x+4000], parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

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

# --- Main App ---
def main():
    db.init_db()  # <-- MANA SHU QATORNI QO'SHISH SHART!
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.job_queue.run_repeating(check_reminders, interval=60, first=5)
    
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("kick", admin_kick_user))

    # Conversation Handlers
    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)
    app.add_handler(group_announce_conv)
    app.add_handler(broadcast_conv)

    # Menyu tugmalari
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_LESSONS}$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SUBSCRIPTIONS}$"), show_user_subscriptions)) # <-- MANA BU QATORNI QO'SHING
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SETTINGS}$"), show_settings))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CREATE_GROUP}$"), start_create_group))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_MANAGE_GROUPS}$"), show_managed_groups))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_GUIDE}$"), show_guide)) # <-- MANA BU QATORNI HAM QO'SHING

    # Aniq patternli Callback'lar
    app.add_handler(CallbackQueryHandler(admin_all_users_callback, pattern="^get_all_subscribers$"))
    app.add_handler(CallbackQueryHandler(ics_download_callback, pattern="^download_ics_"))
    app.add_handler(CallbackQueryHandler(group_members_callback, pattern="^groupmembers_"))
    
    # Qolgan general Callback Query'lar
    app.add_handler(CallbackQueryHandler(toggle_setting_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^(delete_lesson_|dellesson_)"))
    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_)"))

    app.run_polling()

if __name__ == "__main__":
    main()
