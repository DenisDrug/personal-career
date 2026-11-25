# Personal Career 2.0

Сервис ищет вакансии QA Engineer, IT Project Manager, Business Analyst, System Analyst, Product Manager, DevOps, Developer, Data Analyst, Accountant и Designer на Habr Career, Hirify, HH, Talanto, Instahyre и Remote Job, сравнивает их с профилем пользователя и отправляет подходящие вакансии в Telegram.

## MVP в Telegram

1. Пользователь отправляет боту резюме в формате PDF или DOCX через кнопку `📄 Моё резюме`.
2. Бот извлекает текст в памяти и сохраняет в PostgreSQL только структурированный профиль навыков — исходный файл не сохраняется.
3. В `🎯 Настройки поиска` пользователь выбирает одну роль из каталога IT-направлений и порог совпадения 50–80%.
4. В настройках можно выбрать язык вакансий: только русский, русский с техническим английским или любой язык.
5. Поиск из меню отправляет вакансии только выбранной роли. Для каждого пользователя ведётся отдельная история отправок.

В локальном тестовом режиме (`TEST_MODE=true`) доступ разрешён только Telegram ID из `ADMIN_USER_IDS`, поэтому production-бот на сервере не затрагивается.

## Запуск

```bash
cd "services/personal career"
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# Для поиска Instahyre через JavaScript-браузер:
pip install -e '.[browser]'
playwright install chromium-headless-shell
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID и ADMIN_USER_IDS
python -m career.main --once
```

Для локального PostgreSQL запустите Docker Compose и используйте настройки из `.env.local.example`:

```bash
docker compose -f docker-compose.local.yml up -d
cp .env.local.example .env
python -m career.main --once
```

Для постоянного запуска по расписанию 08:00, 12:00, 15:00 и 18:00 (Europe/Minsk):

```bash
python -m career.main
```

Если PDF — сканы без текстового слоя, бот попросит загрузить другой файл. Поддержка OCR будет отдельным следующим шагом.

## Важно

Некоторые сайты могут менять HTML, требовать авторизацию или ограничивать автоматические запросы. Адаптеры изолированы в `career/sources/`, поэтому селекторы можно обновлять отдельно. Сервис не подаёт отклики автоматически — только присылает ссылки.

Instahyre загружается отдельным последовательным headless-сеансом Chromium: бот вводит поисковый запрос в публичную форму, читает видимые карточки и закрывает браузер. Если Playwright или Chromium не установлены либо сайт временно заблокировал браузерный запрос, остальные источники продолжают работать, а Instahyre пропускается с записью ошибки в лог.

Диагностика источников и локальные процедуры Git/deploy/backup описаны в [`docs/`](./docs/).
