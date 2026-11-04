"""SQLite local e migrações aditivas, executadas na primeira inicialização."""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "financas.db"
DEFAULT_CATEGORIES = (
    "Moradia", "Mercado", "Transporte", "Lazer", "Saúde", "Educação",
    "Assinaturas", "Outros",
)

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) > 0)
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) > 0),
    kind TEXT NOT NULL CHECK(kind IN ('corrente','poupanca','dinheiro','credito')),
    initial_balance_cents INTEGER NOT NULL DEFAULT 0
        CHECK(typeof(initial_balance_cents) = 'integer')
);
CREATE TABLE IF NOT EXISTS recurring_rules (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL CHECK(length(trim(description)) > 0),
    amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
    type TEXT NOT NULL CHECK(type IN ('receita','despesa')),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    notes TEXT NOT NULL DEFAULT '',
    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 31),
    start_month TEXT NOT NULL,
    end_month TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    description TEXT NOT NULL CHECK(length(trim(description)) > 0),
    amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
    type TEXT NOT NULL CHECK(type IN ('receita','despesa')),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    notes TEXT NOT NULL DEFAULT '',
    recurrence_id INTEGER REFERENCES recurring_rules(id) ON DELETE SET NULL,
    recurrence_month TEXT,
    import_key TEXT,
    UNIQUE(recurrence_id,recurrence_month)
);
CREATE TABLE IF NOT EXISTS recurrence_runs (
    recurrence_id INTEGER NOT NULL REFERENCES recurring_rules(id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    PRIMARY KEY(recurrence_id,month)
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_import ON transactions(import_key);
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY,
    month TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    limit_cents INTEGER NOT NULL CHECK(typeof(limit_cents)='integer' AND limit_cents>0),
    UNIQUE(month, category_id)
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name))>0),
    target_cents INTEGER NOT NULL CHECK(typeof(target_cents)='integer' AND target_cents>0),
    deadline TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goal_contributions (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
    notes TEXT NOT NULL DEFAULT ''
);
"""


def get_connection(path=None):
    """Cada chamada abre uma conexão; o chamador deve fechá-la ao terminar."""
    target = str(path if path is not None else os.environ.get("FINANCAS_DB_PATH", DEFAULT_DB))
    if target != ":memory:":
        Path(target).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        target = str(Path(target).expanduser())
    db = sqlite3.connect(target, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(db):
    """Migração transacional: categorias padrão inseridas somente na criação."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > 1:
        raise ValueError("Este banco foi criado por uma versão mais recente do aplicativo.")
    if version < 1:
        # executescript controla a própria transação: BEGIN explícito inclui todo o DDL.
        try:
            db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA_V1)
            db.executemany("INSERT OR IGNORE INTO categories(name) VALUES (?)",
                           [(name,) for name in DEFAULT_CATEGORIES])
            db.execute("PRAGMA user_version = 1")
            db.commit()
        except Exception:
            db.rollback()
            raise
