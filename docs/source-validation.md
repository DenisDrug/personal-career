# Проверка источников вакансий

## Что проверяется

Проверка выполняется в двух слоях:

1. Фикстурные тесты разбора HTML/JSON и изоляции ошибок. Они не зависят от доступности сайтов.
2. Контрольный живой запуск `search_all` по одной роли без отправки в Telegram и без записи в БД.

Запуск локальных тестов:

```bash
cd "/Users/vb/Denis/Projects/services/personal career"
./.venv/bin/python -m pytest -q -p no:cacheprovider
```

Контрольный поиск:

```bash
./.venv/bin/python - <<'PY'
from career.sources.web import search_all
search_all(timeout=5, role="qa", debug_logs=True)
PY
```

## Последний контрольный запуск

Дата запуска: 2026-11-25. Роль: `qa`. Результаты агрегированы по источникам:

| Источник | Запросы | Найдено до дедупликации | Ошибки | Результат |
|---|---:|---:|---:|---|
| Hirify | 3 | 45 | 0 | отвечает, HTML разбирается |
| Talanto | 3 | 108 | 0 | отвечает, HTML разбирается |
| Instahyre | 1 | 0 | 1 | пропущен: Chromium не установлен локально |
| Remote Job | 3 | 0 | 3 | TLS connect timeout |
| Habr Career | 3 | 0 | 3 | TLS connect timeout |
| HH | 3 | 0 | 3 | TLS connect timeout |

После дедупликации получено 101 вакансия: 43 с Hirify и 58 с Talanto.

Ошибки одного источника изолированы: процесс продолжает следующий источник и выводит
итоговую статистику. Таймауты Remote Job, Habr и HH требуют повторной проверки из другой
сетевой среды; это не доказывает, что сайты постоянно недоступны.

Для Instahyre необходимо установить браузер Playwright:

```bash
./.venv/bin/python -m pip install -e '.[browser]'
./.venv/bin/playwright install chromium-headless-shell
```

Установка браузера остаётся отдельным локальным шагом и не выполняется автоматически при
поиске, чтобы недоступный Chromium не останавливал остальные источники.
