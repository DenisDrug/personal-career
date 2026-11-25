# Локальная подготовка Git, деплоя и backup

Серверные команды в этом документе не выполняются автоматически. Перед ними нужно
отдельно подтвердить целевой проект, ветку и окно работ.

## Git

```bash
cd "/Users/vb/Denis/Projects/services/personal career"
git status
git diff --check
./.venv/bin/python -m pytest -q -p no:cacheprovider
git add career tests docs pyproject.toml README.md .env.example .gitignore
git commit -m "Improve source diagnostics and search statistics"
git push origin main
```

`.env`, резюме, базы, логи, `.venv` и токены не добавляются в commit.

## Безопасное обновление на сервере

1. Проверить резервную копию PostgreSQL и текущий статус `personal-career.service`.
2. Скачать новую версию в отдельный release-каталог.
3. Установить зависимости в окружение release и выполнить миграции.
4. Проверить импорт и тесты до переключения сервиса.
5. Переключить release-каталог атомарно и перезапустить только `personal-career.service`.
6. Проверить журнал и Telegram-ответ. `fishing-forecast-bot.service` не останавливать.
7. При ошибке вернуть предыдущий release и восстановить БД из backup только если миграция необратима.

## PostgreSQL backup/restore

Пример процедуры для администратора сервера:

```bash
pg_dump --format=custom --file=/var/backups/personal_career_$(date +%F_%H-%M).dump personal_career
pg_restore --clean --if-exists --dbname=personal_career /var/backups/personal_career_YYYY-MM-DD_HH-MM.dump
```

Backup должен храниться с ограниченными правами доступа, иметь срок хранения и регулярно
проверяться восстановлением в отдельную тестовую базу. Файл `.env` и пароль PostgreSQL
не записываются в команды, документацию или Git.
