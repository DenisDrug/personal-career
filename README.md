# Personal Career

Сервис ищет вакансии QA Engineer и IT Project Manager на Habr Career, Hirify, HH, Talanto, Instahyre и Remote Job, сравнивает их с PDF-резюме из директории `resumes/` проекта и отправляет подходящие вакансии в Telegram.

## Запуск

```bash
cd "services/personal career"
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
python -m career.main --once
```

Для постоянного запуска по расписанию 08:00, 12:00, 16:00 и 18:00 (Europe/Minsk):

```bash
python -m career.main
```

Если PDF — сканы без текстового слоя, установите optional-зависимости OCR (`pip install -e '.[ocr]'`) и системные `tesseract`/`poppler`. Без OCR сервис использует профиль навыков из `career/default_profile.py`.

## Важно

Некоторые сайты могут менять HTML, требовать авторизацию или ограничивать автоматические запросы. Адаптеры изолированы в `career/sources/`, поэтому селекторы можно обновлять отдельно. Сервис не подаёт отклики автоматически — только присылает ссылки.
