import asyncio
import re
import threading
from datetime import datetime, timedelta, timezone

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .config import load_settings
from .resumes import extract_resume_text, profile_from_text
from .roles import ROLE_CATALOG, ROLE_KEYS
from .storage import Storage

# Legacy constants are kept so old keyboards already shown in Telegram still work.
SEARCH_BUTTON = "🔎 Поиск вакансий"
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
RESUME_BUTTON = "📄 Моё резюме"
SETTINGS_BUTTON = "🎯 Настройки поиска"
STATS_BUTTON = "📊 Моя статистика"
SEARCH_DAILY_BUTTON = "🆕 Новые выбранные за сутки"
SEARCH_ALL_BUTTON = "📚 Найти все выбранные"
CANCEL_SEARCH_BUTTON = "⏹ Отменить поиск"
CANCEL_SEARCH_CALLBACK = "cancel_search"
RESUME_PREFIX = "resume_slot:"

WELCOME_MESSAGE = (
    "👋 Это Personal Career — бот для поиска подходящих вакансий.\n\n"
    "Он анализирует ваше резюме, сравнивает его с вакансиями и присылает только те "
    "предложения, которые соответствуют вашим навыкам.\n\n"
    "Загрузите резюме, чтобы начать."
)

HELP_MESSAGE = (
    "ℹ️ Personal Career — бот для поиска подходящих IT-вакансий.\n\n"
    "Что умеет бот:\n"
    "• анализировать загруженное резюме;\n"
    "• хранить до двух резюме для разных ролей, например QA и Project Manager;\n"
    "• искать вакансии по одной или нескольким выбранным ролям;\n"
    "• сравнивать вакансии с соответствующим резюме по навыкам;\n"
    "• учитывать язык вакансии и формат работы;\n"
    "• отправлять только новые подходящие вакансии;\n"
    "• выполнять автоматический поиск по расписанию.\n\n"
    "Как начать:\n"
    "1. Откройте «📄 Моё резюме» и загрузите PDF или DOCX.\n"
    "2. В «🎯 Настройки поиска» выберите роли и фильтры.\n"
    "3. Нажмите «🔎 Поиск вакансий» или включите автопоиск.\n\n"
    "Управление выполняется через кнопки меню. Для повторного запуска используйте /start."
)

APPROVE_PREFIX = "user_approve:"
REJECT_PREFIX = "user_reject:"
DELETE_PREFIX = "user_delete:"

_active_searches: dict[str, tuple[asyncio.Task, threading.Event]] = {}


def menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [SEARCH_BUTTON],
        [RESUME_BUTTON, SETTINGS_BUTTON],
        [STATS_BUTTON],
    ]
    if is_admin:
        rows.append([USERS_BUTTON, CLEAR_BUTTON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=False)


def role_submenu_keyboard(role: str) -> ReplyKeyboardMarkup:
    rows = [[role_daily_button(role)], [role_all_button(role)]]
    rows.append([BACK_BUTTON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=False)


def selected_roles_search_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[SEARCH_DAILY_BUTTON], [SEARCH_ALL_BUTTON], [BACK_BUTTON]],
        resize_keyboard=True,
        is_persistent=False,
    )


def role_menu_button(role: str) -> str:
    return f"{ROLE_CATALOG[role]['icon']} {ROLE_CATALOG[role]['menu']}"


def role_daily_button(role: str) -> str:
    return f"🆕 Новые {ROLE_CATALOG[role]['short']} за сутки"


def role_all_button(role: str) -> str:
    return f"📚 Найти все {ROLE_CATALOG[role]['short']}"


def role_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [[role_menu_button(role)] for role in ROLE_KEYS]
    rows.append([BACK_BUTTON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def resume_slot_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    existing = [profile["profile_key"] for profile in profiles]
    keys = list(existing)
    if len(keys) < 2:
        keys.extend(role for role in ROLE_KEYS if role not in existing)
    labels = {
        "default": ("📄 Общее", "Общее"),
    }
    buttons = [
        InlineKeyboardButton(
            ("🔄 Обновить " if role in existing else "➕ Загрузить ")
            + labels.get(role, ("", ROLE_CATALOG[role]["short"]))[0 if role == "default" else 1],
            callback_data=RESUME_PREFIX + role,
        )
        for role in keys
    ]
    return InlineKeyboardMarkup([buttons[index:index + 2] for index in range(0, len(buttons), 2)])


def search_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[CANCEL_SEARCH_BUTTON]], resize_keyboard=True, is_persistent=False)


def cancel_search_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(CANCEL_SEARCH_BUTTON, callback_data=CANCEL_SEARCH_CALLBACK)]]
    )


async def _restore_main_menu(message, is_admin: bool, result_text: str) -> None:
    """Keep the main reply keyboard on the final search result message."""
    await message.reply_text(
        text=result_text,
        reply_markup=menu_keyboard(is_admin),
    )


def _user_info(update: Update) -> tuple[str, str]:
    user = update.effective_user
    if not user:
        return "", ""
    return str(user.id), user.username or ""


def _search_is_active(telegram_id: str) -> bool:
    task_info = _active_searches.get(telegram_id)
    return bool(task_info and not task_info[0].done())


async def _block_menu_during_search(update: Update) -> bool:
    telegram_id, _ = _user_info(update)
    if not telegram_id or not _search_is_active(telegram_id):
        return False
    if update.message:
        await update.message.reply_text(
            "⏳ Поиск ещё выполняется. Дождитесь окончания или нажмите кнопку отмены под сообщением поиска.",
        )
    return True


def _is_admin(telegram_id: str, settings) -> bool:
    return telegram_id in settings.admin_user_ids


def _is_test_user_allowed(telegram_id: str, settings) -> bool:
    return not settings.test_mode or _is_admin(telegram_id, settings)


def _storage(settings) -> Storage:
    return Storage(settings.database_path, settings.database_url)


def _settings_keyboard(preferences: dict) -> InlineKeyboardMarkup:
    selected_roles = set(preferences["roles"])
    threshold = preferences["threshold"]
    role_buttons = [
        InlineKeyboardButton(
            ("✅ " if role in selected_roles else "") + f"{ROLE_CATALOG[role]['icon']} {ROLE_CATALOG[role]['short']}",
            callback_data=f"pref_role:{role}",
        )
        for role in ROLE_KEYS
    ]
    threshold_buttons = [
        InlineKeyboardButton(("✅ " if abs(threshold - value) < 0.001 else "") + f"{int(value * 100)}%", callback_data=f"pref_threshold:{value:.2f}")
        for value in (0.50, 0.60, 0.70, 0.80)
    ]
    language_labels = {
        "ru": "🇷🇺 RU",
        "ru_tech": "🛠 RU + TECH",
        "any": "🌍 ALL",
    }
    language_buttons = [
        InlineKeyboardButton(
            ("✅ " if preferences["language_mode"] == mode else "") + label,
            callback_data=f"pref_language:{mode}",
        )
        for mode, label in language_labels.items()
    ]
    auto_label = "✅ 🕒 Автопоиск включён" if preferences["auto_search_enabled"] else "🕒 Включить автопоиск"
    auto_button = InlineKeyboardButton(auto_label, callback_data="pref_auto:toggle")
    work_format_labels = {"remote": "🏠 Удалённо", "office": "🏢 Офис / гибрид"}
    work_format_buttons = [
        InlineKeyboardButton(
            ("✅ " if preferences["work_format"] == mode else "") + label,
            callback_data=f"pref_format:{mode}",
        )
        for mode, label in work_format_labels.items()
    ]
    rows = [role_buttons[index:index + 2] for index in range(0, len(role_buttons), 2)]
    rows.append(threshold_buttons)
    rows.append(language_buttons)
    rows.append(work_format_buttons)
    rows.append([auto_button])
    return InlineKeyboardMarkup(rows)


def _settings_text(preferences: dict, has_profile: bool) -> str:
    roles = ", ".join(
        f"{ROLE_CATALOG[role]['icon']} {ROLE_CATALOG[role]['menu']}"
        for role in preferences["roles"] if role in ROLE_CATALOG
    ) or "не выбраны"
    language_names = {
        "ru": "только русский",
        "ru_tech": "русский + технический английский",
        "any": "любой",
    }
    language = language_names[preferences["language_mode"]]
    auto_search = (
        "включён: 08:00, 12:00, 15:00, 18:00"
        if preferences["auto_search_enabled"]
        else "выключен, только ручной запуск"
    )
    work_format = "удалённая" if preferences["work_format"] == "remote" else "офисная / гибридная"
    resume_text = "загружено" if has_profile else "не загружено"
    return (
        "🎯 Настройки поиска\n\n"
        f"Роли: {roles or 'не выбраны'}\n"
        f"Минимальное совпадение: {preferences['threshold']:.0%}\n"
        f"Язык вакансий: {language}\n"
        f"Автопоиск: {auto_search}\n"
        f"Формат работы: {work_format}\n"
        f"Резюме: {resume_text}\n\n"
        "Нажмите кнопку, чтобы изменить настройку."
    )


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
    if not _is_test_user_allowed(telegram_id, settings):
        return False, False, None
    storage = Storage(settings.database_path, settings.database_url)
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
    if await _block_menu_during_search(update):
        return
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    existing_user = _storage(settings).get_user(telegram_id) if telegram_id else None
    allowed, is_admin, user = await _access_status(update, context, notify_pending=True)
    if not update.message:
        return
    if allowed:
        text = WELCOME_MESSAGE if existing_user is None else "Выберите действие:"
        await update.message.reply_text(text, reply_markup=menu_keyboard(is_admin))
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message:
        return
    if not allowed:
        await update.message.reply_text("Для начала работы отправьте команду /start.")
        return
    await update.message.reply_text(HELP_MESSAGE, reply_markup=menu_keyboard(is_admin))


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id, _ = _user_info(update)
    if update.message and telegram_id:
        await update.message.reply_text(f"Ваш Telegram ID: {telegram_id}")


async def resume_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if not update.message or not allowed:
        return
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    profiles = await asyncio.to_thread(lambda: _storage(settings).list_profiles(telegram_id))
    if not profiles:
        await update.message.reply_text(
            "📄 Резюме ещё не загружено. Выберите роль, затем отправьте PDF или DOCX.",
            reply_markup=resume_slot_keyboard([]),
        )
        return
    lines = ["📄 Мои резюме\n"]
    for profile in profiles:
        parsed = profile["profile"]
        detected_roles = ", ".join(parsed.get("roles", [])) or "не определены автоматически"
        lines.append(
            f"{ROLE_CATALOG.get(profile['profile_key'], {'icon': '📄', 'short': 'Общее'})['icon']} "
            f"{ROLE_CATALOG.get(profile['profile_key'], {'short': 'Общее'})['short']}: {profile['filename']}\n"
            f"Роли в резюме: {detected_roles}; навыков: {len(parsed.get('skills', []))}; "
            f"английский: {parsed.get('english_level', 'не указан')}\n"
        )
    lines.append("Выберите роль, чтобы заменить или добавить резюме (максимум 2).")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=resume_slot_keyboard(profiles),
    )


async def search_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if not update.message or not allowed:
        return
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    stats = await asyncio.to_thread(lambda: _storage(settings).get_search_stats(telegram_id))
    last_search = stats["last_search_at"] or "ещё не выполнялся"
    await update.message.reply_text(
        "📊 Моя статистика\n\n"
        f"Запусков поиска: {stats['search_count']}\n"
        f"Найдено вакансий: {stats['jobs_collected']}\n"
        f"Подошло по фильтрам: {stats['jobs_matched']}\n"
        f"Отправлено в Telegram: {stats['jobs_sent']}\n"
        f"Последний поиск: {last_search}",
        reply_markup=menu_keyboard(_is_admin(telegram_id, settings)),
    )


async def resume_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed, _, _ = await _access_status(update, context)
    if not update.message or not update.message.document or not allowed:
        return
    document = update.message.document
    filename = document.file_name or "resume"
    if not filename.lower().endswith((".pdf", ".docx")):
        await update.message.reply_text("Поддерживаются только файлы PDF и DOCX.")
        return
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("Файл слишком большой. Максимальный размер — 10 МБ.")
        return
    try:
        telegram_file = await context.bot.get_file(document.file_id)
        content = bytes(await telegram_file.download_as_bytearray())
        text = await asyncio.to_thread(extract_resume_text, filename, content)
        if len(text.strip()) < 80:
            await update.message.reply_text(
                "Не удалось извлечь достаточно текста. Проверьте, что PDF не является сканом без текстового слоя."
            )
            return
        settings = load_settings()
        profile = await asyncio.to_thread(profile_from_text, text, settings.extra_skills)
        telegram_id, _ = _user_info(update)
        storage = _storage(settings)
        profile_key = context.user_data.pop("resume_role", "default")
        existing_profiles = await asyncio.to_thread(storage.list_profiles, telegram_id)
        existing_keys = {item["profile_key"] for item in existing_profiles}
        if profile_key not in existing_keys and len(existing_keys) >= 2:
            await update.message.reply_text("Можно хранить не более двух резюме. Обновите одно из существующих.")
            return
        await asyncio.to_thread(
            lambda: storage.save_profile(telegram_id, filename, document.file_id, profile, profile_key=profile_key)
        )
        roles = ", ".join(profile.get("roles", [])) or "не определены автоматически"
        await update.message.reply_text(
            f"✅ Резюме сохранено для роли: {ROLE_CATALOG.get(profile_key, {'short': 'Общее'})['short']}.\n"
            f"Роли распознаны в тексте: {roles}\nРаспознано навыков: {len(profile.get('skills', []))}\n"
            "Исходный файл не сохраняется — хранится только структурированный профиль навыков."
        )
    except Exception as exc:
        print(f"Resume upload failed: {exc!r}", flush=True)
        await update.message.reply_text("Не удалось обработать резюме. Попробуйте другой PDF или DOCX.")


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if not update.message or not allowed:
        return
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    storage = _storage(settings)
    preferences = await asyncio.to_thread(storage.get_preferences, telegram_id)
    profiles = await asyncio.to_thread(storage.list_profiles, telegram_id)
    await update.message.reply_text(
        _settings_text(preferences, bool(profiles)),
        reply_markup=_settings_keyboard(preferences),
    )


async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str | tuple[str, ...], daily: bool) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message or not update.effective_chat:
        return
    if not allowed:
        await update.message.reply_text("Доступ ещё не одобрен администратором.")
        return
    roles = tuple(dict.fromkeys(role)) if isinstance(role, (tuple, list)) else (role,)
    period = "за последние 24 часа" if daily else "за весь доступный период"
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    storage = _storage(settings)
    profiles = {}
    for selected_role in roles:
        profile_record = await asyncio.to_thread(storage.get_profile_for_role, telegram_id, selected_role)
        if profile_record:
            profiles[selected_role] = profile_record
    preferences = await asyncio.to_thread(storage.get_preferences, telegram_id)
    if not profiles:
        await update.message.reply_text(
            "Сначала загрузите резюме для выбранной роли: нажмите «📄 Моё резюме», "
            "выберите роль и отправьте PDF или DOCX.",
            reply_markup=menu_keyboard(is_admin),
        )
        return
    disabled = [selected_role for selected_role in roles if selected_role not in preferences["roles"]]
    if disabled:
        await update.message.reply_text(
            "Выбранные роли отключены в настройках поиска. Откройте «🎯 Настройки поиска»."
        )
        return
    roles = tuple(selected_role for selected_role in roles if selected_role in profiles)
    missing = [selected_role for selected_role in preferences["roles"] if selected_role not in profiles]
    if not roles:
        await update.message.reply_text(
            "Для выбранных ролей нет загруженного резюме. Откройте «📄 Моё резюме» и добавьте его."
        )
        return
    role_names = ", ".join(ROLE_CATALOG[selected_role]["short"] for selected_role in roles)
    missing_text = "\nНе загружено: " + ", ".join(ROLE_CATALOG[item]["short"] for item in missing) if missing else ""
    await update.message.reply_text(
        f"Ищу вакансии: {role_names} {period}...{missing_text}\n"
        "Другие действия временно недоступны. Поиск можно остановить кнопкой ниже.",
        reply_markup=cancel_search_inline_keyboard(),
    )
    from .main import run_once

    since = datetime.now(timezone.utc) - timedelta(hours=24) if daily else None
    cancel_event = threading.Event()

    async def execute_search() -> None:
        current_task = asyncio.current_task()
        result_text = "Поиск завершён. Отправлено новых вакансий: 0."
        try:
            sent = await asyncio.to_thread(
                run_once,
                since=since,
                chat_id=str(update.effective_chat.id),
                role=roles,
                skip_sent=True,
                mark_sent=True,
                profiles={selected_role: profiles[selected_role]["profile"] for selected_role in roles},
                threshold=preferences["threshold"],
                user_id=telegram_id,
                cancel_event=cancel_event,
                language_mode=preferences["language_mode"],
                work_format=preferences["work_format"],
            )
            cancelled = cancel_event.is_set()
            result = "Поиск остановлен" if cancelled else "Поиск завершён"
            result_text = f"{result}. Отправлено новых вакансий: {sent}."
        except Exception as exc:
            print(f"User search failed: {exc!r}", flush=True)
            result_text = "Поиск завершился с ошибкой. Главное меню восстановлено."
        finally:
            if _active_searches.get(telegram_id, (None, None))[0] is current_task:
                _active_searches.pop(telegram_id, None)
            try:
                await _restore_main_menu(update.effective_message, is_admin, result_text)
            except Exception as exc:
                print(f"Failed to restore main menu after search: {exc!r}", flush=True)

    task = asyncio.create_task(execute_search())
    _active_searches[telegram_id] = (task, cancel_event)


async def qa_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "qa", daily=False)


async def qa_daily_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "qa", daily=True)


async def qa_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if update.message and allowed:
        await update.message.reply_text("Выберите тип поиска QA:", reply_markup=role_submenu_keyboard("qa"))


async def pm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if update.message and allowed:
        await update.message.reply_text("Выберите тип поиска PM:", reply_markup=role_submenu_keyboard("pm"))


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, is_admin, _ = await _access_status(update, context)
    if update.message and allowed:
        await update.message.reply_text("Главное меню:", reply_markup=menu_keyboard(is_admin))


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain that the MVP is controlled through buttons, instead of ignoring text."""
    if not update.message:
        return
    if await _block_menu_during_search(update):
        return
    allowed, is_admin, _ = await _access_status(update, context)
    if not allowed:
        await update.message.reply_text("Для начала работы отправьте команду /start.")
        return
    await update.message.reply_text(
        "ℹ️ Я пока работаю через кнопки меню и не обрабатываю свободный текст.\n"
        "Выберите нужное действие ниже.",
        reply_markup=menu_keyboard(is_admin),
    )


async def pm_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "pm", daily=False)


async def pm_daily_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await collection(update, context, "pm", daily=True)


async def search_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if not update.message or not allowed:
        return
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    preferences = await asyncio.to_thread(_storage(settings).get_preferences, telegram_id)
    roles = preferences["roles"] or ("qa",)
    role_names = ", ".join(ROLE_CATALOG[role]["short"] for role in roles)
    await update.message.reply_text(
        f"Выберите тип поиска для ролей: {role_names}",
        reply_markup=selected_roles_search_keyboard(),
    )


async def selected_roles_collection(update: Update, context: ContextTypes.DEFAULT_TYPE, daily: bool) -> None:
    settings = load_settings()
    telegram_id, _ = _user_info(update)
    preferences = await asyncio.to_thread(_storage(settings).get_preferences, telegram_id)
    await collection(update, context, preferences["roles"], daily=daily)


async def selected_roles_daily_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await selected_roles_collection(update, context, daily=True)


async def selected_roles_all_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await selected_roles_collection(update, context, daily=False)


async def role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, _, _ = await _access_status(update, context)
    if not update.message or not allowed:
        return
    role = next((key for key in ROLE_KEYS if update.message.text == role_menu_button(key)), "")
    if role:
        await update.message.reply_text(
            f"Выберите тип поиска: {ROLE_CATALOG[role]['menu']}",
            reply_markup=role_submenu_keyboard(role),
        )


async def role_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    text = update.message.text or ""
    for role in ROLE_KEYS:
        if text == role_daily_button(role):
            await collection(update, context, role, daily=True)
            return
        if text == role_all_button(role):
            await collection(update, context, role, daily=False)
            return


async def resume_slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith(RESUME_PREFIX):
        return
    settings = load_settings()
    telegram_id = str(query.from_user.id)
    allowed, _, _ = await _access_status(update, context)
    if not allowed:
        await query.answer("Доступ не одобрен", show_alert=True)
        return
    role = query.data.removeprefix(RESUME_PREFIX)
    if role != "default" and role not in ROLE_CATALOG:
        await query.answer("Неизвестная роль", show_alert=True)
        return
    storage = _storage(settings)
    profiles = await asyncio.to_thread(storage.list_profiles, telegram_id)
    if role not in {profile["profile_key"] for profile in profiles} and len(profiles) >= 2:
        await query.answer("Уже загружено 2 резюме", show_alert=True)
        return
    context.user_data["resume_role"] = role
    await query.answer("Роль выбрана")
    if query.message:
        await query.message.reply_text(
            f"Отправьте PDF или DOCX резюме для роли {ROLE_CATALOG.get(role, {'short': 'Общее'})['short']}. "
            "Файл будет обработан в памяти, исходник не сохраняется."
        )


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id, _ = _user_info(update)
    task_info = _active_searches.get(telegram_id)
    if not update.message:
        return
    if not task_info or task_info[0].done():
        await update.message.reply_text("Активного поиска нет.", reply_markup=menu_keyboard(_is_admin(telegram_id, load_settings())))
        return
    task_info[1].set()
    await update.message.reply_text(
        "⏹ Останавливаю поиск. Текущий сетевой запрос завершится, после этого появится результат.",
    )


async def cancel_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    telegram_id = str(query.from_user.id)
    task_info = _active_searches.get(telegram_id)
    if not task_info or task_info[0].done():
        await query.answer("Поиск уже завершён")
        return
    task_info[1].set()
    await query.answer("Останавливаю поиск")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message:
        return
    if not allowed or not is_admin:
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    settings = load_settings()
    deleted = await asyncio.to_thread(lambda: Storage(settings.database_path, settings.database_url).clear_sent())
    await update.message.reply_text(
        f"История очищена. Удалено записей: {deleted}. Следующий поиск начнётся заново.",
        reply_markup=menu_keyboard(True),
    )


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _block_menu_during_search(update):
        return
    allowed, is_admin, _ = await _access_status(update, context)
    if not update.message:
        return
    if not allowed or not is_admin:
        await update.message.reply_text("Просмотр пользователей доступен только администратору.")
        return
    settings = load_settings()
    users = await asyncio.to_thread(lambda: Storage(settings.database_path, settings.database_url).list_users())
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
    storage = Storage(settings.database_path, settings.database_url)
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


async def _process_preferences_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    settings = load_settings()
    telegram_id = str(query.from_user.id)
    if not _is_test_user_allowed(telegram_id, settings):
        await query.answer("Доступ не одобрен", show_alert=True)
        return
    storage = _storage(settings)
    user = storage.get_user(telegram_id)
    if not _is_admin(telegram_id, settings) and (not user or user["status"] != "approved"):
        await query.answer("Доступ не одобрен", show_alert=True)
        return
    preferences = storage.get_preferences(telegram_id)
    action, value = query.data.split(":", 1)
    if action == "pref_role":
        if value not in ROLE_CATALOG:
            await query.answer("Неизвестная роль", show_alert=True)
            return
        roles = list(preferences["roles"])
        if value in roles:
            if len(roles) == 1:
                await query.answer("Нужно выбрать хотя бы одну роль", show_alert=True)
                return
            roles.remove(value)
        else:
            roles.append(value)
        storage.save_preferences(
            telegram_id,
            tuple(roles),
            preferences["threshold"],
            preferences["language_mode"],
            preferences["auto_search_enabled"],
            preferences["work_format"],
        )
    elif action == "pref_threshold":
        try:
            threshold = float(value)
        except ValueError:
            await query.answer("Некорректный порог", show_alert=True)
            return
        if not 0.0 < threshold <= 1.0:
            await query.answer("Некорректный порог", show_alert=True)
            return
        storage.save_preferences(
            telegram_id,
            preferences["roles"],
            threshold,
            preferences["language_mode"],
            preferences["auto_search_enabled"],
            preferences["work_format"],
        )
    elif action == "pref_language":
        if value not in {"ru", "ru_tech", "any"}:
            await query.answer("Неизвестный режим языка", show_alert=True)
            return
        storage.save_preferences(
            telegram_id,
            preferences["roles"],
            preferences["threshold"],
            value,
            preferences["auto_search_enabled"],
            preferences["work_format"],
        )
    elif action == "pref_auto":
        if value != "toggle":
            await query.answer("Неизвестная настройка", show_alert=True)
            return
        storage.save_preferences(
            telegram_id,
            preferences["roles"],
            preferences["threshold"],
            preferences["language_mode"],
            not preferences["auto_search_enabled"],
            preferences["work_format"],
        )
    elif action == "pref_format":
        if value not in {"remote", "office"}:
            await query.answer("Неизвестный формат работы", show_alert=True)
            return
        storage.save_preferences(
            telegram_id,
            preferences["roles"],
            preferences["threshold"],
            preferences["language_mode"],
            preferences["auto_search_enabled"],
            value,
        )
    else:
        await query.answer("Неизвестная настройка", show_alert=True)
        return
    preferences = storage.get_preferences(telegram_id)
    profiles = storage.list_profiles(telegram_id)
    await query.answer("Настройка сохранена")
    try:
        await query.edit_message_text(
            _settings_text(preferences, bool(profiles)),
            reply_markup=_settings_keyboard(preferences),
        )
    except TelegramError:
        pass


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    print(
        f"Telegram callback received: data={getattr(query, 'data', None)!r}, "
        f"user_id={getattr(getattr(query, 'from_user', None), 'id', None)!r}",
        flush=True,
    )
    try:
        if query and query.data == CANCEL_SEARCH_CALLBACK:
            await cancel_search_callback(update, context)
        elif query and query.data and query.data.startswith(RESUME_PREFIX):
            await resume_slot_callback(update, context)
        elif query and query.data and query.data.startswith("pref_"):
            await _process_preferences_callback(update, context)
        else:
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


def _buttons_filter(labels: tuple[str, ...]):
    pattern = "^(?:" + "|".join(re.escape(label) for label in labels) + ")$"
    return filters.Regex(pattern)


def run_bot(token: str) -> None:
    async def register_commands(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "Запустить бота"),
            BotCommand("help", "Что умеет бот"),
            BotCommand("myid", "Показать Telegram ID"),
        ])

    application = Application.builder().token(token).post_init(register_commands).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CallbackQueryHandler(approval_callback))
    application.add_handler(MessageHandler(_button_filter(SEARCH_BUTTON), search_menu))
    application.add_handler(MessageHandler(_button_filter(SEARCH_DAILY_BUTTON), selected_roles_daily_collection))
    application.add_handler(MessageHandler(_button_filter(SEARCH_ALL_BUTTON), selected_roles_all_collection))
    application.add_handler(MessageHandler(_buttons_filter(tuple(role_menu_button(role) for role in ROLE_KEYS)), role_selection))
    application.add_handler(
        MessageHandler(
            _buttons_filter(tuple(button for role in ROLE_KEYS for button in (role_daily_button(role), role_all_button(role)))),
            role_search,
        )
    )
    application.add_handler(MessageHandler(_button_filter(QA_BUTTON), qa_menu))
    application.add_handler(MessageHandler(_button_filter(QA_DAILY_BUTTON), qa_daily_collection))
    application.add_handler(MessageHandler(_button_filter(QA_ALL_BUTTON), qa_collection))
    application.add_handler(MessageHandler(_button_filter(PM_BUTTON), pm_menu))
    application.add_handler(MessageHandler(_button_filter(PM_DAILY_BUTTON), pm_daily_collection))
    application.add_handler(MessageHandler(_button_filter(PM_ALL_BUTTON), pm_collection))
    application.add_handler(MessageHandler(_button_filter(LEGACY_QA_DAILY_BUTTON), qa_daily_collection))
    application.add_handler(MessageHandler(_button_filter(LEGACY_PM_DAILY_BUTTON), pm_daily_collection))
    application.add_handler(MessageHandler(_button_filter(CANCEL_SEARCH_BUTTON), cancel_search))
    application.add_handler(MessageHandler(_button_filter(BACK_BUTTON), back_to_menu))
    application.add_handler(MessageHandler(_button_filter(CLEAR_BUTTON), clear_history))
    application.add_handler(MessageHandler(_button_filter(USERS_BUTTON), list_users))
    application.add_handler(MessageHandler(_button_filter(RESUME_BUTTON), resume_status))
    application.add_handler(MessageHandler(_button_filter(STATS_BUTTON), search_statistics))
    application.add_handler(MessageHandler(_button_filter(SETTINGS_BUTTON), settings_menu))
    application.add_handler(MessageHandler(filters.Document.ALL, resume_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    # Keep pending callback queries across restarts. Dropping them makes admin
    # approval/deletion buttons appear completely unresponsive after deploys.
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        stop_signals=None,
    )
