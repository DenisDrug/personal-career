import asyncio
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .config import load_settings
from .storage import Storage

QA_BUTTON = "🔎 QA вакансии"
QA_DAILY_BUTTON = "🕘 QA за сутки"
PM_BUTTON = "📋 PM вакансии"
PM_DAILY_BUTTON = "🕘 PM за сутки"
CLEAR_BUTTON = "🗑 Очистить историю"
USERS_BUTTON = "👥 Пользователи"

APPROVE_PREFIX = "user_approve:"
REJECT_PREFIX = "user_reject:"


def menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [QA_BUTTON, QA_DAILY_BUTTON],
        [PM_BUTTON, PM_DAILY_BUTTON],
    ]
    if is_admin:
        rows.append([USERS_BUTTON, CLEAR_BUTTON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _user_info(update: Update) -> tuple[str, str]:
    user = update.effective_user
    if not user:
        return "", ""
    return str(user.id), user.username or ""


def _is_admin(telegram_id: str, settings) -> bool:
    return telegram_id in settings.admin_user_ids


async def _notify_admins(context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    settings = load_settings()
    username = f"@{user['username']}" if user["username"] else "не указан"
    text = (
        "🔔 Новый пользователь хочет подключиться\n\n"
        f"ID: <code>{user['telegram_id']}</code>\n"
        f"Никнейм: {username}"
    )
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Одобрить", callback_data=APPROVE_PREFIX + user["telegram_id"]),
            InlineKeyboardButton("❌ Отклонить", callback_data=REJECT_PREFIX + user["telegram_id"]),
        ]]
    )
    for admin_id in settings.admin_chat_ids:
        await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML", reply_markup=keyboard)


async def _access_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, bool, dict | None]:
    settings = load_settings()
    telegram_id, username = _user_info(update)
    if not telegram_id:
        return False, False, None
    storage = Storage(settings.database_path)
    user = storage.get_user(telegram_id)
    if user is None:
        storage.upsert_user(telegram_id, username=username)
        user = storage.get_user(telegram_id)
        if not _is_admin(telegram_id, settings):
            await _notify_admins(context, user)
    else:
        storage.upsert_user(telegram_id, username=username)
        user = storage.get_user(telegram_id)
    is_admin = _is_admin(telegram_id, settings)
    if is_admin and user and user["status"] != "approved":
        storage.set_user_status(telegram_id, "approved")
        user = storage.get_user(telegram_id)
    return bool(is_admin or (user and user["status"] == "approved")), is_admin, user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, is_admin, user = await _access_status(update, context)
    if not update.message:
        return
    if allowed:
        await update.message.reply_text("Выберите действие:", reply_markup=menu_keyboard(is_admin))
    elif user and user["status"] == "pending":
        await update.message.reply_text(
            "Заявка отправлена администратору. Ожидайте подтверждения.",
        )
    else:
        await update.message.reply_text("Доступ к боту запрещён.")


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id, _ = _user_info(update)
    if update.message and telegram_id:
        await update.message.reply_text(f"Ваш Telegram ID: {telegram_id}")


async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str, daily: bool) -> None:
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message or not update.effective_chat:
        return
    if not allowed:
        await update.message.reply_text("Доступ ещё не одобрен администратором.")
        return
    period = "за последние 24 часа" if daily else "за весь доступный период"
    await update.message.reply_text(f"Ищу {role.upper()} вакансии {period}...")
    from .main import run_once

    since = datetime.now(timezone.utc) - timedelta(hours=24) if daily else None
    sent = await asyncio.to_thread(
        run_once,
        since=since,
        chat_id=str(update.effective_chat.id),
        role=role,
        skip_sent=True,
        mark_sent=True,
    )
    await update.message.reply_text(
        f"Готово. Отправлено новых вакансий: {sent}.",
        reply_markup=menu_keyboard(is_admin),
    )


async def qa_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "qa", daily=False)


async def qa_daily_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "qa", daily=True)


async def pm_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "pm", daily=False)


async def pm_daily_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "pm", daily=True)


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message:
        return
    if not allowed or not is_admin:
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    settings = load_settings()
    deleted = await asyncio.to_thread(lambda: Storage(settings.database_path).clear_sent())
    await update.message.reply_text(
        f"История очищена. Удалено записей: {deleted}. Следующий поиск начнётся заново.",
        reply_markup=menu_keyboard(True),
    )


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message:
        return
    if not allowed or not is_admin:
        await update.message.reply_text("Просмотр пользователей доступен только администратору.")
        return
    settings = load_settings()
    users = await asyncio.to_thread(lambda: Storage(settings.database_path).list_users())
    if not users:
        await update.message.reply_text("Пользователей пока нет.", reply_markup=menu_keyboard(True))
        return
    lines = ["👥 Пользователи бота:"]
    for user in users:
        username = f"@{user['username']}" if user["username"] else "без никнейма"
        phone = user["phone"] or "телефон не указан"
        lines.append(f"{user['status']} · {user['telegram_id']} · {username} · {phone}")
    await update.message.reply_text("\n".join(lines), reply_markup=menu_keyboard(True))


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    settings = load_settings()
    admin_id = str(query.from_user.id)
    if not _is_admin(admin_id, settings):
        await query.answer("Недостаточно прав", show_alert=True)
        return
    await query.answer()
    if not query.data or ":" not in query.data:
        await query.edit_message_text("Некорректная заявка.")
        return
    action, telegram_id = query.data.split(":", 1)
    storage = Storage(settings.database_path)
    user = storage.get_user(telegram_id)
    if not user:
        await query.edit_message_text("Пользователь не найден в БД.")
        return
    status = "approved" if action == "user_approve" else "rejected"
    storage.set_user_status(telegram_id, status)
    await query.edit_message_text(f"Пользователь {telegram_id}: {status}")
    if status == "approved":
        await context.bot.send_message(chat_id=telegram_id, text="✅ Доступ одобрен администратором.", reply_markup=menu_keyboard())
    else:
        await context.bot.send_message(chat_id=telegram_id, text="❌ Доступ к боту отклонён администратором.")


def _button_filter(label: str):
    return filters.Regex(f"^{re.escape(label)}$")


def run_bot(token: str) -> None:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^user_(approve|reject):"))
    application.add_handler(MessageHandler(_button_filter(QA_BUTTON), qa_collection))
    application.add_handler(MessageHandler(_button_filter(QA_DAILY_BUTTON), qa_daily_collection))
    application.add_handler(MessageHandler(_button_filter(PM_BUTTON), pm_collection))
    application.add_handler(MessageHandler(_button_filter(PM_DAILY_BUTTON), pm_daily_collection))
    application.add_handler(MessageHandler(_button_filter(CLEAR_BUTTON), clear_history))
    application.add_handler(MessageHandler(_button_filter(USERS_BUTTON), list_users))
    application.run_polling(drop_pending_updates=True, stop_signals=None)
