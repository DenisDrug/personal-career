import asyncio
from datetime import datetime, timedelta, timezone

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

DAILY_BUTTON = "Подборка за сутки"


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[DAILY_BUTTON]], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Выберите действие:",
            reply_markup=menu_keyboard(),
        )


async def daily_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    await update.message.reply_text("Ищу подходящие вакансии, опубликованные за последние 24 часа...")
    from .main import run_once

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    sent = await asyncio.to_thread(
        run_once,
        since=since,
        chat_id=str(update.effective_chat.id),
        skip_sent=False,
        mark_sent=False,
    )
    await update.message.reply_text(
        f"Готово. Отправлено вакансий: {sent}.",
        reply_markup=menu_keyboard(),
    )


def run_bot(token: str) -> None:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(f"^{DAILY_BUTTON}$"), daily_collection))
    application.run_polling(drop_pending_updates=True, stop_signals=None)
