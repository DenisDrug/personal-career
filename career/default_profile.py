DEFAULT_PROFILE = {
    "roles": ["qa engineer", "quality assurance", "тестировщик", "it project manager", "project manager"],
    "skills": {
        "qa": [
            "manual testing", "functional testing", "api testing", "postman", "sql",
            "jira", "test cases", "test documentation", "regression testing", "smoke testing",
            "bug tracking", "test plans", "agile", "scrum", "git",
        ],
        "pm": [
            "project management", "project manager", "stakeholder management", "agile",
            "scrum", "kanban", "jira", "confluence", "risk management", "roadmap",
            "requirements", "planning", "budget", "team management", "коммуникация",
        ],
    },
}

SKILL_ALIASES = {
    "manual testing": ("ручное тестирование", "ручной тестировщик", "manual qa", "manual tester"),
    "functional testing": ("функциональное тестирование", "функциональное", "functional test"),
    "api testing": ("тестирование api", "api test", "rest api", "api"),
    "test cases": ("тест-кейсы", "тест кейсы", "тестовые сценарии", "test case"),
    "test documentation": ("тестовая документация", "тестовой документацией", "документация по тестированию"),
    "regression testing": ("регрессионное тестирование", "regression test"),
    "smoke testing": ("smoke", "smoke test", "смоук", "смоук-тестирование", "smoke testing"),
    "bug tracking": ("баг-репорт", "баг-репорты", "баг-трекинг", "отслеживание ошибок", "дефекты", "defect tracking"),
    "test plans": ("план тестирования", "планы тестирования"),
    "project management": ("управление проектами", "ведение проектов"),
    "stakeholder management": ("стейкхолдеры", "заинтересованные стороны"),
    "risk management": ("управление рисками", "риски проекта"),
    "requirements": ("требования", "сбор требований", "анализ требований"),
    "planning": ("планирование", "план проекта"),
    "budget": ("бюджет", "бюджетирование"),
    "team management": ("управление командой", "команда проекта"),
    "roadmap": ("дорожная карта", "план развития"),
    "communication": ("коммуникация", "взаимодействие", "переговоры"),
    "agile": ("гибкая методология", "гибкие методологии"),
    "sql": ("sql", "реляционная бд", "реляционные бд", "реляционная база данных", "реляционные базы данных", "простые sql-запросы"),
}
