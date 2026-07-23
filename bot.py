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

# --- Keyboards ---
BTN_LESSONS = "📚 Mening Darslarim"
BTN_SETTINGS = "⚙️ Eslatma Sozlamalari"
BTN_CREATE_GROUP = "➕ Yangi Guruh Yaratish"
BTN_MANAGE_GROUPS = "📂 Guruhlarimni Boshqarish"
BTN_BACK = "⬅️ Orqaga"

def main_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_LESSONS), KeyboardButton(BTN_SETTINGS)],
        [KeyboardButton(BTN_CREATE_GROUP), KeyboardButton(BTN_MANAGE_GROUPS)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

cancel_keyboard = ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)

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
            await update.message.reply_text("❌ Guruh topilmadi yoki havola eskirgan.", reply_markup=main_menu_keyboard())

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
        "Qaysi vaqtlarda shaxsiy lichkangizga eslatma kelishini tanlang:"
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
async def start_create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Yangi guruh nomini kiriting:",
        reply_markup=cancel_keyboard
    )
    return WAIT_GROUP_NAME

async def cancel_group_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Jarayon bekor qilindi.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def save_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        group_name = update.message.text.strip()
        user_id = update.effective_user.id
        db.create_group(group_name, user_id)

        await update.message.reply_text(
            f"✅ **{group_name}** guruhi yaratildi!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )
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
        "Format:\n"
        "`Dars Nomi`\n`Ustoz`\n`Zoom Link (-)`\n`YYYY-MM-DD HH:MM`"
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

    await update.message.reply_text(
        f"✅ Jami **{added_count}** ta dars qo'shildi!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )
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

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    if not has_lessons:
        await update.message.reply_text("Yaqin orada rejalashtirilgan darslar yo'q.", reply_markup=main_menu_keyboard())

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

# --- GROUP ANNOUNCEMENT (CRASH ISHLAMAYDI) ---
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

    # SQLite dan xavfsiz a'zolarni olish
    with db.get_db() as conn:
        subscribers = conn.execute("SELECT telegram_id FROM subscriptions WHERE group_id = ?", (gid,)).fetchall()

    if not subscribers:
        await msg.reply_text("❌ Ushbu guruhda a'zolar yo'q.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    sent_count, failed_count = 0, 0
    announce_text = f"📢 **E'LON [{group['name']}]**\n\n{msg.text}"

    for sub in subscribers:
        u_id = sub["telegram_id"]
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
        f"• Faol darslar: **{total_lessons} ta**"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Barcha Obunachilar Ro'yxati", callback_data="admin_all_users")],
        [InlineKeyboardButton("📢 Xabar tarqatish", callback_data="admin_broadcast")]
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != SUPER_ADMIN_ID:
        return

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
            text += f"{idx}. Telegram Foydalanuvchisi — `ID: {uid}`\n"

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await query.message.reply_text(text[x:x+4000], parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

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
    user_ids = db.get_all_users_list()

    sent_count, failed_count = 0, 0
    for u_id in user_ids:
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
    app = ApplicationBuilder().token(BOT_TOKEN).build()

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

    # Handlers
    app.add_handler(create_group_conv)
    app.add_handler(add_lesson_conv)
    app.add_handler(group_announce_conv)
    app.add_handler(broadcast_conv)

    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SETTINGS}$"), show_settings))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_LESSONS}$"), show_student_lessons))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_MANAGE_GROUPS}$"), show_managed_groups))

    app.add_handler(CallbackQueryHandler(admin_all_users_callback, pattern="^admin_all_users$"))
    app.add_handler(CallbackQueryHandler(toggle_setting_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(list_lessons_callback, pattern="^listlessons_"))
    app.add_handler(CallbackQueryHandler(delete_lesson_callback, pattern="^(delete_lesson_|dellesson_)"))
    app.add_handler(CallbackQueryHandler(group_manage_callback, pattern="^(managegroup_|delgroup_)"))

    app.run_polling()

if __name__ == "__main__":
    main()
