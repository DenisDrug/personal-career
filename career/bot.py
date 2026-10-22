import asyncio
import re
from datetime import datetime, timedelta, timezone

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

QA_BUTTON = "QA вакансии"
QA_DAILY_BUTTON = "QA за сутки"
PM_BUTTON = "PM вакансии"
PM_DAILY_BUTTON = "PM за сутки"
CLEAR_BUTTON = "Очистить историю"


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [QA_BUTTON, QA_DAILY_BUTTON],
            [PM_BUTTON, PM_DAILY_BUTTON],
            [CLEAR_BUTTON],
        ],
        resize_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Выберите тип поиска:", reply_markup=menu_keyboard())


async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str, daily: bool) -> None:
    if not update.message or not update.effective_chat:
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
        reply_markup=menu_keyboard(),
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
    if not update.message:
        return
    from .config import load_settings
    from .storage import Storage

    settings = load_settings()
    deleted = await asyncio.to_thread(Storage(settings.database_path).clear_sent)
    await update.message.reply_text(
        f"История очищена. Удалено записей: {deleted}. Следующий поиск начнётся заново.",
        reply_markup=menu_keyboard(),
    )


def _button_filter(label: str):
    return filters.Regex(f"^{re.escape(label)}$")


def run_bot(token: str) -> None:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(_button_filter(QA_BUTTON), qa_collection))
    application.add_handler(MessageHandler(_button_filter(QA_DAILY_BUTTON), qa_daily_collection))
    application.add_handler(MessageHandler(_button_filter(PM_BUTTON), pm_collection))
    application.add_handler(MessageHandler(_button_filter(PM_DAILY_BUTTON), pm_daily_collection))
    application.add_handler(MessageHandler(_button_filter(CLEAR_BUTTON), clear_history))
    application.run_polling(drop_pending_updates=True, stop_signals=None)
