import asyncio
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .config import load_settings
from .storage import Storage

QA_BUTTON = "🔎 QA вакансии"
PM_BUTTON = "📋 PM вакансии"
QA_DAILY_BUTTON = "🆕 Новые QA за сутки"
QA_ALL_BUTTON = "📚 Найти все QA"
PM_DAILY_BUTTON = "🆕 Новые PM за сутки"
PM_ALL_BUTTON = "📚 Найти все PM"
BACK_BUTTON = "↩️ Назад"
# Keep handling old keyboard messages that may still be visible in Telegram.
LEGACY_QA_DAILY_BUTTON = "🕘 QA за сутки"
LEGACY_PM_DAILY_BUTTON = "🕘 PM за сутки"
CLEAR_BUTTON = "🗑 Очистить историю"
USERS_BUTTON = "👥 Пользователи"

APPROVE_PREFIX = "user_approve:"
REJECT_PREFIX = "user_reject:"
DELETE_PREFIX = "user_delete:"


def menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [QA_BUTTON],
        [PM_BUTTON],
    ]
    if is_admin:
        rows.append([USERS_BUTTON, CLEAR_BUTTON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def role_submenu_keyboard(role: str) -> ReplyKeyboardMarkup:
    if role == "qa":
        rows = [[QA_DAILY_BUTTON], [QA_ALL_BUTTON]]
    else:
        rows = [[PM_DAILY_BUTTON], [PM_ALL_BUTTON]]
    rows.append([BACK_BUTTON])
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


async def _notify_user(context: ContextTypes.DEFAULT_TYPE, telegram_id: str, text: str, reply_markup=None) -> bool:
    try:
        await context.bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)
        return True
    except TelegramError:
        return False


async def _report_admin_action(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    edited = False
    try:
        await query.edit_message_text(text)
        edited = True
    except TelegramError:
        pass
    if query.message:
        if not edited:
            await context.bot.send_message(chat_id=query.message.chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"ℹ️ {text}")


async def _access_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    notify_pending: bool = False,
) -> tuple[bool, bool, dict | None]:
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
        if user["status"] == "rejected":
            if storage.request_access(telegram_id):
                user = storage.get_user(telegram_id)
                if not _is_admin(telegram_id, settings):
                    await _notify_admins(context, user)
            else:
                user = storage.get_user(telegram_id)
        if notify_pending and user["status"] == "pending" and not _is_admin(telegram_id, settings):
            await _notify_admins(context, user)
    is_admin = _is_admin(telegram_id, settings)
    if is_admin and user and user["status"] != "approved":
        storage.set_user_status(telegram_id, "approved")
        user = storage.get_user(telegram_id)
    return bool(is_admin or (user and user["status"] == "approved")), is_admin, user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, is_admin, user = await _access_status(update, context, notify_pending=True)
    if not update.message:
        return
    if allowed:
        await update.message.reply_text("Выберите действие:", reply_markup=menu_keyboard(is_admin))
    elif user and user["status"] == "pending":
        await update.message.reply_text(
            "Заявка отправлена администратору. Ожидайте подтверждения.",
        )
    elif user and user.get("retry_after"):
        retry_after = user["retry_after"].replace("+00:00", " UTC")
        await update.message.reply_text(
            f"Повторные заявки временно заблокированы до {retry_after}. Попробуйте позже.",
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


async def qa_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, _, _ = await _access_status(update, context)
    if update.message and allowed:
        await update.message.reply_text("Выберите тип поиска QA:", reply_markup=role_submenu_keyboard("qa"))


async def pm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, _, _ = await _access_status(update, context)
    if update.message and allowed:
        await update.message.reply_text("Выберите тип поиска PM:", reply_markup=role_submenu_keyboard("pm"))


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, is_admin, _ = await _access_status(update, context)
    if update.message and allowed:
        await update.message.reply_text("Главное меню:", reply_markup=menu_keyboard(is_admin))


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
    await update.message.reply_text("👥 Пользователи бота:")
    for user in users:
        username = f"@{user['username']}" if user["username"] else "без никнейма"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Удалить пользователя", callback_data=DELETE_PREFIX + user["telegram_id"])
        ]])
        await update.message.reply_text(
            f"👤 Никнейм: {username}\n🆔 ID: {user['telegram_id']}",
            reply_markup=keyboard,
        )
    await update.message.reply_text("Выберите действие:", reply_markup=menu_keyboard(True))


async def _process_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if action not in {"user_approve", "user_reject", "user_delete"}:
        await _report_admin_action(query, context, "⚠️ Неизвестное действие.")
        return
    storage = Storage(settings.database_path)
    user = storage.get_user(telegram_id)
    if not user:
        await _report_admin_action(query, context, "⚠️ Пользователь не найден в БД.")
        return
    if action == "user_delete":
        deleted = storage.delete_user(telegram_id)
        if not deleted:
            await _report_admin_action(query, context, "⚠️ Пользователь уже удалён.")
            return
        await _report_admin_action(query, context, f"🗑 Пользователь {telegram_id} удалён из БД.")
        notified = await _notify_user(
            context,
            telegram_id,
            "🗑 Ваша учётная запись удалена администратором. Для новой заявки отправьте /start.",
        )
        if not notified:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"ℹ️ Запись удалена, но уведомить пользователя {telegram_id} не удалось.",
            )
        return
    status = "approved" if action == "user_approve" else "rejected"
    user = storage.set_user_status(telegram_id, status) if status == "approved" else storage.reject_user(telegram_id)
    status_text = "одобрен" if status == "approved" else "отклонён"
    await _report_admin_action(query, context, f"Пользователь {telegram_id} {status_text}.")
    if status == "approved":
        notified = await _notify_user(
            context,
            telegram_id,
            "✅ Ваша заявка одобрена. Доступ к поиску вакансий открыт.",
            reply_markup=menu_keyboard(),
        )
    else:
        cooldown_text = " После третьего отклонения новые заявки будут доступны через 30 дней."
        notified = await _notify_user(
            context,
            telegram_id,
            "❌ Ваша заявка отклонена администратором." + cooldown_text,
        )
    if not notified and query.message:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"ℹ️ Решение сохранено, но уведомить пользователя {telegram_id} не удалось.",
        )


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    print(
        f"Telegram callback received: data={getattr(query, 'data', None)!r}, "
        f"user_id={getattr(getattr(query, 'from_user', None), 'id', None)!r}",
        flush=True,
    )
    try:
        await _process_approval_callback(update, context)
    except Exception as exc:
        print(f"Telegram callback failed: {exc!r}", flush=True)
        if query:
            try:
                await query.answer("Ошибка обработки действия", show_alert=True)
            except TelegramError:
                pass


def _button_filter(label: str):
    return filters.Regex(f"^{re.escape(label)}$")


def run_bot(token: str) -> None:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CallbackQueryHandler(approval_callback))
    application.add_handler(MessageHandler(_button_filter(QA_BUTTON), qa_menu))
    application.add_handler(MessageHandler(_button_filter(QA_DAILY_BUTTON), qa_daily_collection))
    application.add_handler(MessageHandler(_button_filter(QA_ALL_BUTTON), qa_collection))
    application.add_handler(MessageHandler(_button_filter(PM_BUTTON), pm_menu))
    application.add_handler(MessageHandler(_button_filter(PM_DAILY_BUTTON), pm_daily_collection))
    application.add_handler(MessageHandler(_button_filter(PM_ALL_BUTTON), pm_collection))
    application.add_handler(MessageHandler(_button_filter(LEGACY_QA_DAILY_BUTTON), qa_daily_collection))
    application.add_handler(MessageHandler(_button_filter(LEGACY_PM_DAILY_BUTTON), pm_daily_collection))
    application.add_handler(MessageHandler(_button_filter(BACK_BUTTON), back_to_menu))
    application.add_handler(MessageHandler(_button_filter(CLEAR_BUTTON), clear_history))
    application.add_handler(MessageHandler(_button_filter(USERS_BUTTON), list_users))
    # Keep pending callback queries across restarts. Dropping them makes admin
    # approval/deletion buttons appear completely unresponsive after deploys.
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        stop_signals=None,
    )
