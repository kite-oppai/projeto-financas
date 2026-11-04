"""Cria uma base demonstrativa separada, sem tocar nas finanças pessoais."""

from __future__ import annotations

import argparse
import calendar
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from database.core import get_connection, initialize


DEFAULT_DEMO_PATH = Path(__file__).resolve().parent / "data" / "demo.db"


def _month_offset(today: date, offset: int) -> date:
    absolute = today.year * 12 + today.month - 1 + offset
    year, month = divmod(absolute, 12)
    return date(year, month + 1, 1)


def _check_existing(path: Path) -> bool:
    """Retorna True para demo já criada; recusa todo outro banco existente."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as existing:
            row = existing.execute(
                "SELECT version FROM demo_seed_marker WHERE id = 1"
            ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(
            "O arquivo já existe e não é uma base de demonstração reconhecida. "
            "Escolha um novo caminho com --db; nenhum dado foi substituído."
        ) from exc
    if row != (1,):
        raise ValueError("Base de demonstração não reconhecida; escolha outro arquivo.")
    return True


def seed_demo(path: str | Path = DEFAULT_DEMO_PATH, *, today: date | None = None) -> bool:
    """Popula uma base nova. Retorna False se já era uma demo, sem duplicar dados."""
    path = Path(path).expanduser().resolve()
    if _check_existing(path):
        return False
    today = today or date.today()
    db = get_connection(path)
    try:
        initialize(db)
        categories = {
            row["name"].casefold(): row["id"]
            for row in db.execute("SELECT id, name FROM categories")
        }
        with db:
            checking = db.execute(
                "INSERT INTO accounts(name, kind, initial_balance_cents) VALUES (?, ?, ?)",
                ("Conta de exemplo", "corrente", 250_000),
            ).lastrowid
            card = db.execute(
                "INSERT INTO accounts(name, kind, initial_balance_cents) VALUES (?, ?, ?)",
                ("Cartão de exemplo", "credito", 0),
            ).lastrowid
            for offset in (-2, -1, 0):
                month = _month_offset(today, offset)
                items = [
                    (5, "Salário de exemplo", 650_000, "receita", "outros", checking),
                    (8, "Aluguel de exemplo", 160_000, "despesa", "moradia", checking),
                    (10, "Supermercado de exemplo", 42_590 + offset * 1_000, "despesa", "mercado", card),
                    (12, "Transporte de exemplo", 18_000, "despesa", "transporte", checking),
                    (15, "Cinema e passeio", 12_500, "despesa", "lazer", card),
                    (18, "Consulta de exemplo", 28_000, "despesa", "saúde", checking),
                    (20, "Curso de exemplo", 15_990, "despesa", "educação", card),
                    (22, "Assinatura de exemplo", 3_990, "despesa", "assinaturas", card),
                    (25, "Trabalho extra de exemplo", 45_000, "receita", "outros", checking),
                ]
                for day, description, cents, kind, category, account in items:
                    db.execute(
                        "INSERT INTO transactions "
                        "(date, description, amount_cents, type, category_id, account_id, notes) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (month.replace(day=day).isoformat(), description, cents, kind,
                         categories[category], account, "Dado fictício para demonstração"),
                    )
            current_month = today.strftime("%Y-%m")
            for category, limit in (("moradia", 250_000), ("mercado", 50_000), ("lazer", 10_000)):
                db.execute(
                    "INSERT INTO budgets(month, category_id, limit_cents) VALUES (?, ?, ?)",
                    (current_month, categories[category], limit),
                )
            next_month = _month_offset(today, 1)
            db.execute(
                "INSERT INTO recurring_rules "
                "(description, amount_cents, type, category_id, account_id, notes, day, "
                "start_month, end_month, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("Assinatura recorrente de exemplo", 3_990, "despesa",
                 categories["assinaturas"], card, "Começa no próximo mês", 22,
                 next_month.strftime("%Y-%m"), None, 1),
            )
            deadline_month = _month_offset(today, 6)
            deadline = deadline_month.replace(
                day=min(today.day, calendar.monthrange(deadline_month.year, deadline_month.month)[1])
            )
            goal = db.execute(
                "INSERT INTO goals(name, target_cents, deadline) VALUES (?, ?, ?)",
                ("Reserva de emergência (exemplo)", 1_000_000, deadline.isoformat()),
            ).lastrowid
            db.execute(
                "INSERT INTO goal_contributions(goal_id, date, amount_cents, notes) "
                "VALUES (?, ?, ?, ?)",
                (goal, today.isoformat(), 250_000, "Aporte fictício; não altera saldo da conta"),
            )
            db.execute(
                "CREATE TABLE demo_seed_marker "
                "(id INTEGER PRIMARY KEY CHECK(id = 1), version INTEGER NOT NULL)"
            )
            db.execute("INSERT INTO demo_seed_marker(id, version) VALUES (1, 1)")
    finally:
        db.close()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DEMO_PATH,
        help="Caminho de um banco novo; padrão: data/demo.db. Nunca sobrescreve outro banco.",
    )
    args = parser.parse_args()
    try:
        created = seed_demo(args.db)
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f"Não foi possível preparar a demonstração: {exc}\n")
    print("Demonstração criada." if created else "Demonstração já existente; nenhum dado duplicado.")
    print(f"Banco: {args.db.expanduser().resolve()}")
    print("Para abrir, defina FINANCAS_DB_PATH com esse caminho e execute streamlit run app.py.")


if __name__ == "__main__":
    main()
