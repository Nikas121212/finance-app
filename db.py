import sqlite3
from datetime import date
from contextlib import contextmanager

DB_PATH = "finance.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    comment TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    target_amount REAL NOT NULL,
    saved_amount REAL NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL CHECK(direction IN ('i_owe', 'owed_to_me')),
    counterparty TEXT NOT NULL,
    amount REAL NOT NULL,
    date_created TEXT NOT NULL,
    comment TEXT DEFAULT '',
    closed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recurring_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    day_of_month INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS advice_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    question_type TEXT NOT NULL,
    input_amount REAL,
    advice_text TEXT NOT NULL
);
"""

DEFAULT_GOALS = [
    ("Подушка на мёртвый сезон", 150000, 1),
    ("Рекламная кампания", 100000, 2),
    ("Курс по продажам", 80000, 3),
]

DEFAULT_DEBTS = [
    ("i_owe", "Друг", 15000, "Личный долг"),
    ("i_owe", "Коммуналка", 15000, "Задолженность по коммунальным платежам"),
]

DEFAULT_TEMPLATES = [
    ("Аренда рабочего места", "expense", "Аренда места", 22000, 1),
    ("Коммуналка", "expense", "Коммуналка", 5000, 1),
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT COUNT(*) FROM goals")
        if cur.fetchone()[0] == 0:
            for name, target, priority in DEFAULT_GOALS:
                conn.execute(
                    "INSERT INTO goals (name, target_amount, saved_amount, priority) VALUES (?, ?, 0, ?)",
                    (name, target, priority),
                )
        cur = conn.execute("SELECT COUNT(*) FROM debts")
        if cur.fetchone()[0] == 0:
            for direction, counterparty, amount, comment in DEFAULT_DEBTS:
                conn.execute(
                    "INSERT INTO debts (direction, counterparty, amount, date_created, comment, closed) VALUES (?, ?, ?, ?, ?, 0)",
                    (direction, counterparty, amount, date.today().isoformat(), comment),
                )
        cur = conn.execute("SELECT COUNT(*) FROM recurring_templates")
        if cur.fetchone()[0] == 0:
            for name, kind, category, amount, day in DEFAULT_TEMPLATES:
                conn.execute(
                    "INSERT INTO recurring_templates (name, kind, category, amount, day_of_month) VALUES (?, ?, ?, ?, ?)",
                    (name, kind, category, amount, day),
                )


INCOME_CATEGORIES = ["Тату-сеансы", "Побочные заказы"]
EXPENSE_CATEGORIES_BUSINESS = ["Расходники", "Оборудование", "Аренда места", "Реклама"]
EXPENSE_CATEGORIES_PERSONAL = ["Коммуналка", "Продукты", "Прочее личное"]
EXPENSE_CATEGORIES = EXPENSE_CATEGORIES_BUSINESS + EXPENSE_CATEGORIES_PERSONAL
