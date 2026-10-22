from html import escape

import httpx

from .models import Match


def send_match(token: str, chat_id: str, match: Match, timeout: float) -> None:
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")
    job = match.job
    text = (
        f"<b>{escape(job.title)}</b>\n"
        f"{escape(job.company or 'Компания не указана')} · {escape(job.location or 'Локация не указана')}\n"
        f"Совпадение: <b>{match.score:.0%}</b>\n"
        f"Навыки: {escape(', '.join(match.matched_skills) or 'не определены')}\n"
        f"Источник: {escape(job.source)}\n\n<a href=\"{escape(job.url, quote=True)}\">Открыть вакансию</a>"
    )
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
        timeout=timeout,
    )
    response.raise_for_status()
