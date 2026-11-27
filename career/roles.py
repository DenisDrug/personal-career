"""Single source of truth for supported IT job roles."""

ROLE_CATALOG = {
    "qa": {
        "icon": "🧪",
        "menu": "QA и тестирование",
        "short": "QA",
        "queries": ("QA Engineer", "Manual QA", "тестировщик"),
        "remote_query": "QA",
        "title_terms": ("qa", "quality assurance", "тестировщик", "тестировщик", "tester", "test engineer", "инженер по тестированию"),
        "resume_terms": ("qa engineer", "manual qa", "qa-инженер", "qa инженер", "тестировщик", "автотест", "инженер по тестированию"),
        "skills": (
            "manual testing", "functional testing", "regression testing", "smoke testing", "sanity testing",
            "integration testing", "system testing", "acceptance testing", "exploratory testing", "usability testing",
            "compatibility testing", "cross-browser testing", "mobile testing", "api testing", "rest api",
            "postman", "swagger", "sql", "test cases", "test scenarios", "test documentation", "test plans",
            "checklists", "bug tracking", "defect management", "jira", "testrail", "xray", "testlink",
            "allure", "selenium", "playwright", "cypress", "appium", "android studio", "browserstack",
            "chrome devtools", "wordpress", "git", "ci/cd", "testing theory", "test design", "boundary value analysis",
            "equivalence partitioning", "mentoring",
        ),
    },
    "pm": {
        "icon": "📋",
        "menu": "Управление проектами",
        "short": "PM",
        "queries": ("IT Project Manager", "Project Manager", "менеджер проектов"),
        "remote_query": "Project Manager",
        "title_terms": ("project manager", "project management", "менеджер проектов", "руководитель проектов"),
        "resume_terms": ("project manager", "project management", "менеджер проектов", "управление проектами", "руководитель проектов"),
        "skills": (
            "project management", "project manager", "stakeholder management", "client management", "agile",
            "scrum", "kanban", "waterfall", "hybrid methodology", "jira", "confluence", "trello", "asana",
            "risk management", "issue management", "change management", "roadmap", "requirements",
            "scope management", "planning", "estimation", "budget", "cost management", "team management",
            "resource management", "vendor management", "delivery management", "release planning", "OKR",
            "KPI", "project management theory", "communication", "negotiation", "mentoring", "reporting",
        ),
    },
    "business_analyst": {
        "icon": "📊",
        "menu": "Бизнес-аналитика",
        "short": "Business Analyst",
        "queries": ("Business Analyst", "бизнес-аналитик"),
        "remote_query": "Business Analyst",
        "title_terms": ("business analyst", "бизнес аналитик", "бизнес-аналитик"),
        "resume_terms": ("business analyst", "бизнес аналитик", "бизнес-аналитик"),
        "skills": (
            "requirements", "business requirements", "functional requirements", "non-functional requirements",
            "requirements analysis", "sql", "bpmn", "uml", "user stories", "use cases", "acceptance criteria",
            "process modeling", "business process analysis", "business process management", "as is to be",
            "jira", "confluence", "юзабилити", "аналитика", "data analysis", "stakeholder management",
            "workshops", "documentation", "прототипирование",
        ),
    },
    "system_analyst": {
        "icon": "🧩",
        "menu": "Системная аналитика",
        "short": "System Analyst",
        "queries": ("System Analyst", "системный аналитик"),
        "remote_query": "System Analyst",
        "title_terms": ("system analyst", "системный аналитик"),
        "resume_terms": ("system analyst", "системный аналитик"),
        "skills": (
            "requirements", "functional requirements", "technical requirements", "system requirements", "sql",
            "api testing", "rest api", "soap", "swagger", "openapi", "json", "xml", "uml", "bpmn",
            "sequence diagrams", "data modeling", "database design", "integration", "интеграции", "microservices",
            "event-driven architecture", "kafka", "rabbitmq", "technical documentation", "system design",
            "acceptance criteria", "user stories", "use cases", "jira", "confluence", "postman",
        ),
    },
    "product_manager": {
        "icon": "🚀",
        "menu": "Product Management",
        "short": "Product Manager",
        "queries": ("Product Manager", "продакт-менеджер", "менеджер продукта"),
        "remote_query": "Product Manager",
        "title_terms": ("product manager", "продакт менеджер", "продакт-менеджер", "менеджер продукта"),
        "resume_terms": ("product manager", "продакт менеджер", "продакт-менеджер", "менеджер продукта"),
        "skills": (
            "product management", "product strategy", "product vision", "roadmap", "backlog management",
            "prioritization", "discovery", "customer development", "user research", "customer interviews",
            "analytics", "product analytics", "requirements", "user stories", "jobs to be done", "agile", "scrum",
            "a/b testing", "метрики", "kpi", "okr", "unit economics", "retention", "conversion rate", "funnel",
            "monetization", "market research", "competitor analysis", "figma", "jira", "confluence",
        ),
    },
    "devops": {
        "icon": "⚙️",
        "menu": "DevOps и инфраструктура",
        "short": "DevOps",
        "queries": ("DevOps Engineer", "DevOps", "инженер DevOps"),
        "remote_query": "DevOps",
        "title_terms": ("devops", "dev ops", "инженер devops", "sre", "site reliability"),
        "resume_terms": ("devops", "dev ops", "инженер devops", "sre", "site reliability"),
        "skills": (
            "linux", "bash", "shell scripting", "docker", "docker compose", "kubernetes", "helm", "ci/cd",
            "git", "gitlab ci", "github actions", "jenkins", "teamcity", "aws", "azure", "gcp", "terraform",
            "ansible", "pulumi", "monitoring", "prometheus", "grafana", "elk", "loki", "logging", "observability",
            "nginx", "haproxy", "networking", "dns", "http", "ssl", "security", "secrets management",
            "vault", "argocd", "istio", "postgresql", "mysql", "redis", "sre", "high availability",
        ),
    },
    "developer": {
        "icon": "💻",
        "menu": "Разработка",
        "short": "Developer",
        "queries": ("Software Developer", "Software Engineer", "разработчик"),
        "remote_query": "Software Developer",
        "title_terms": ("software developer", "software engineer", "разработчик", "программист", "backend", "frontend", "fullstack"),
        "resume_terms": ("software developer", "software engineer", "разработчик", "программист", "backend", "frontend", "fullstack"),
        # These phrases describe cooperation with developers, not the candidate's role.
        "resume_exclude_contexts": (
            "взаимодействую с разработчиками",
            "взаимодействовал с разработчиками",
            "взаимодействовала с разработчиками",
            "взаимодействие с разработчиками",
            "работал с разработчиками",
            "работала с разработчиками",
            "работа с разработчиками",
            "командой разработчиков",
            "команда разработчиков",
            "разработчиками аналитиками",
            "разработчиками и аналитиками",
        ),
        "skills": (
            "python", "javascript", "typescript", "java", "kotlin", "go", "c#", "c++", "php", "ruby",
            "sql", "git", "rest api", "graphql", "grpc", "docker", "юнит-тесты", "unit testing", "integration testing",
            "solid", "design patterns", "algorithms", "data structures", "oop", "microservices", "message queues",
            "rabbitmq", "kafka", "postgresql", "mysql", "mongodb", "redis", "django", "fastapi", "spring",
            "react", "vue", "angular", "node.js", "ci/cd", "code review", "linux", "agile", "scrum",
        ),
    },
    "data_analyst": {
        "icon": "📈",
        "menu": "Аналитика данных",
        "short": "Data Analyst",
        "queries": ("Data Analyst", "аналитик данных"),
        "remote_query": "Data Analyst",
        "title_terms": ("data analyst", "аналитик данных", "дата аналитик"),
        "resume_terms": ("data analyst", "аналитик данных", "дата аналитик"),
        "skills": (
            "sql", "python", "r", "excel", "power bi", "tableau", "looker", "data studio", "analytics",
            "статистика", "метрики", "data visualization", "дашборды", "reporting", "etl", "elt", "data cleaning",
            "data modeling", "a/b testing", "hypothesis testing", "regression analysis", "cohort analysis",
            "funnel analysis", "retention", "conversion rate", "product analytics", "postgresql", "mysql",
            "clickhouse", "bigquery", "jupyter", "pandas", "numpy", "airflow", "dbt",
        ),
    },
    "accountant": {
        "icon": "💰",
        "menu": "Accountant / Бухгалтерия",
        "short": "Accountant",
        "queries": ("Accountant", "бухгалтер", "главный бухгалтер"),
        "remote_query": "Accountant",
        "title_terms": ("accountant", "бухгалтер", "главный бухгалтер", "финансовый бухгалтер"),
        "resume_terms": ("accountant", "бухгалтер", "главный бухгалтер", "финансовый бухгалтер"),
        "skills": (
            "1c", "DipIFR", "ACCA", "бухгалтерский учет", "налоговый учет", "управленческий учет", "мсфо", "рсбу", "excel",
            "отчетность", "бухгалтерская отчетность", "финансовая отчетность", "зарплата", "расчет зарплаты",
            "налоги", "налоговая отчетность", "первичная документация", "банк клиент", "клиент-банк", "авансовые отчеты",
            "касса", "взаиморасчеты", "дебиторская задолженность", "кредиторская задолженность", "учет основных средств",
            "закрытие месяца", "восстановление учета", "налоговое планирование", "консультант плюс", "контур",
            "сверка расчетов", "инвентаризация", "финансовый контроль", "erp", "управление командой",
        ),
    },
    "designer": {
        "icon": "🎨",
        "menu": "Дизайн",
        "short": "Designer",
        "queries": ("UI/UX Designer", "Product Designer", "дизайнер"),
        "remote_query": "Designer",
        "title_terms": ("designer", "дизайнер", "ux", "ui/ux", "product designer", "графический дизайнер"),
        "resume_terms": ("designer", "дизайнер", "ux", "ui/ux", "product designer", "графический дизайнер"),
        "skills": (
            "figma", "sketch", "adobe photoshop", "adobe illustrator", "adobe xd", "invision", "zeplin",
            "ui design", "ux design", "product design", "web design", "graphic design", "motion design",
            "прототипирование", "wireframes", "дизайн интерфейсов", "исследование пользователей", "user research",
            "usability testing", "customer journey map", "user flow", "design system", "design tokens", "typography",
            "color theory", "веб-дизайн", "графический дизайн", "анимация", "3d", "html", "css", "accessibility",
            "a/b testing", "конкурентный анализ", "презентации", "брендинг", "иллюстрация", "генеративный дизайн",
        ),
    },
}

ROLE_KEYS = tuple(ROLE_CATALOG)


def normalize_role_text(text: str) -> str:
    """Make role matching tolerant of PDF hyphens, line breaks and separators."""
    normalized = text.lower().replace("ё", "е")
    for separator in ("-", "–", "—", "‑", "/", "\\", ",", ";", ":"):
        normalized = normalized.replace(separator, " ")
    return " ".join(normalized.split())


def role_for_text(text: str, *, field: str = "title") -> str:
    normalized = normalize_role_text(text)
    terms_key = "title_terms" if field == "title" else "resume_terms"
    for key, role in ROLE_CATALOG.items():
        if role_matches_text(normalized, key, field=field, already_normalized=True):
            return key
    return ""


def role_matches_text(text: str, role_key: str, *, field: str = "resume", already_normalized: bool = False) -> bool:
    """Return whether text contains a role marker, excluding known non-role contexts."""
    role = ROLE_CATALOG[role_key]
    normalized = text if already_normalized else normalize_role_text(text)
    terms_key = "title_terms" if field == "title" else "resume_terms"
    for term in role[terms_key]:
        marker = normalize_role_text(term)
        position = normalized.find(marker)
        while position >= 0:
            if field != "resume" or not any(
                normalize_role_text(context) in normalized[max(0, position - 90): position + len(marker) + 90]
                for context in role.get("resume_exclude_contexts", ())
            ):
                return True
            position = normalized.find(marker, position + 1)
    return False
