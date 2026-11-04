"""Regras de lançamentos, cadastros, orçamento e consultas financeiras."""

import calendar
import sqlite3
from datetime import date, timedelta

from services.money import clean_text, require_cents, validate_date, validate_month

ACCOUNT_KINDS = ("corrente", "poupanca", "dinheiro", "credito")
TRANSACTION_TYPES = ("receita", "despesa")


def _rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


def _exists(db, table, identifier, label):
    if not isinstance(identifier, int) or isinstance(identifier, bool):
        raise ValueError(f"{label} inválido(a).")
    if db.execute(f"SELECT 1 FROM {table} WHERE id=?", (identifier,)).fetchone() is None:
        raise ValueError(f"{label} não encontrado(a).")


def _write(db, sql, values, duplicate_message="Este nome já está em uso."):
    try:
        with db:
            cursor = db.execute(sql, values)
            if cursor.rowcount == 0:
                raise ValueError("Registro não encontrado.")
            return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError(duplicate_message) from exc


def list_categories(db):
    return _rows(db.execute("SELECT * FROM categories ORDER BY name COLLATE NOCASE"))


def create_category(db, name):
    return _write(db, "INSERT INTO categories(name) VALUES (?)", (clean_text(name, "Categoria"),))


def update_category(db, id, name):
    _write(db, "UPDATE categories SET name=? WHERE id=?", (clean_text(name, "Categoria"), id))


def delete_category(db, id):
    _write(db, "DELETE FROM categories WHERE id=?", (id,),
           "Categoria em uso por lançamentos, orçamentos ou recorrências. Remova os vínculos primeiro.")


def list_accounts(db):
    return _rows(db.execute("""
        SELECT a.*, a.initial_balance_cents + COALESCE(SUM(
            CASE t.type WHEN 'receita' THEN t.amount_cents ELSE -t.amount_cents END
        ),0) AS balance_cents
        FROM accounts a LEFT JOIN transactions t ON t.account_id=a.id
        GROUP BY a.id ORDER BY a.name COLLATE NOCASE
    """))


def _account_values(name, kind, initial_balance_cents):
    if kind not in ACCOUNT_KINDS:
        raise ValueError("Tipo de conta inválido.")
    return clean_text(name, "Nome da conta"), kind, require_cents(initial_balance_cents, positive=False)


def create_account(db, name, kind, initial_balance_cents=0):
    return _write(db, "INSERT INTO accounts(name,kind,initial_balance_cents) VALUES (?,?,?)",
                  _account_values(name, kind, initial_balance_cents))


def update_account(db, id, name, kind, initial_balance_cents=0):
    values = _account_values(name, kind, initial_balance_cents)
    _write(db, "UPDATE accounts SET name=?,kind=?,initial_balance_cents=? WHERE id=?", (*values, id))


def delete_account(db, id):
    _write(db, "DELETE FROM accounts WHERE id=?", (id,),
           "Conta em uso por lançamentos ou recorrências. Remova os vínculos primeiro.")


def transaction_values(db, date, description, amount_cents, type, category_id, account_id, notes=""):
    """Validação compartilhada; não grava nem confirma transações."""
    if type not in TRANSACTION_TYPES:
        raise ValueError("Tipo inválido. Escolha receita ou despesa.")
    _exists(db, "categories", category_id, "Categoria")
    _exists(db, "accounts", account_id, "Conta")
    if not isinstance(notes, str) or len(notes) > 5000:
        raise ValueError("A observação deve ter no máximo 5.000 caracteres.")
    return (validate_date(date), clean_text(description, "Descrição"), require_cents(amount_cents),
            type, category_id, account_id, notes.strip())


TRANSACTION_SELECT = """
    SELECT t.*, c.name AS category_name, a.name AS account_name
    FROM transactions t JOIN categories c ON c.id=t.category_id
    JOIN accounts a ON a.id=t.account_id
"""


def list_transactions(db, month=None):
    if month is not None:
        validate_month(month)
        return _rows(db.execute(TRANSACTION_SELECT +
            " WHERE substr(t.date,1,7)=? ORDER BY t.date DESC,t.id DESC", (month,)))
    return _rows(db.execute(TRANSACTION_SELECT + " ORDER BY t.date DESC,t.id DESC"))


def get_transaction(db, id):
    row = db.execute(TRANSACTION_SELECT + " WHERE t.id=?", (id,)).fetchone()
    if row is None:
        raise ValueError("Lançamento não encontrado.")
    return dict(row)


def create_transaction(db, date, description, amount_cents, type, category_id, account_id, notes=""):
    values = transaction_values(db, date, description, amount_cents, type, category_id, account_id, notes)
    return _write(db, """INSERT INTO transactions
        (date,description,amount_cents,type,category_id,account_id,notes) VALUES (?,?,?,?,?,?,?)""", values,
        "Não foi possível salvar o lançamento. Verifique os campos.")


def update_transaction(db, id, date, description, amount_cents, type, category_id, account_id, notes=""):
    values = transaction_values(db, date, description, amount_cents, type, category_id, account_id, notes)
    # A chave original da importação deixa de descrever o lançamento após uma edição.
    _write(db, """UPDATE transactions SET date=?,description=?,amount_cents=?,type=?,
        category_id=?,account_id=?,notes=?,import_key=NULL WHERE id=?""", (*values, id),
        "Não foi possível editar o lançamento. Verifique os campos.")


def delete_transaction(db, id):
    # recurrence_runs permanece: excluir uma ocorrência não a recria no próximo acesso.
    _write(db, "DELETE FROM transactions WHERE id=?", (id,))


def set_budget(db, month, category_id, limit_cents):
    validate_month(month)
    require_cents(limit_cents)
    _exists(db, "categories", category_id, "Categoria")
    _write(db, """INSERT INTO budgets(month,category_id,limit_cents) VALUES (?,?,?)
        ON CONFLICT(month,category_id) DO UPDATE SET limit_cents=excluded.limit_cents""",
        (month, category_id, limit_cents))


def delete_budget(db, id):
    _write(db, "DELETE FROM budgets WHERE id=?", (id,))


def budget_status(db, month):
    validate_month(month)
    rows = _rows(db.execute("""
        SELECT b.*,c.name AS category_name,COALESCE(SUM(t.amount_cents),0) AS spent_cents
        FROM budgets b JOIN categories c ON c.id=b.category_id
        LEFT JOIN transactions t ON t.category_id=b.category_id AND t.type='despesa'
            AND substr(t.date,1,7)=b.month
        WHERE b.month=? GROUP BY b.id ORDER BY c.name COLLATE NOCASE
    """, (month,)))
    for row in rows:
        spent, limit = row["spent_cents"], row["limit_cents"]
        row["remaining_cents"] = limit - spent
        row["status"] = ("excedido" if spent >= limit else
                         "atencao" if spent * 100 >= limit * 80 else "normal")
    return rows


def _totals(db, month):
    totals = {row["type"]: row["total"] for row in db.execute("""
        SELECT type,SUM(amount_cents) AS total FROM transactions
        WHERE substr(date,1,7)=? GROUP BY type
    """, (month,))}
    income, expense = totals.get("receita", 0), totals.get("despesa", 0)
    return {"income_cents": income, "expense_cents": expense, "balance_cents": income - expense}


def monthly_summary(db, month):
    validate_month(month)
    start = date.fromisoformat(month + "-01")
    previous = (start - timedelta(days=1)).strftime("%Y-%m") if start.year > 1 or start.month > 1 else None
    totals = _totals(db, month)
    before = _totals(db, previous) if previous else {k: 0 for k in totals}
    totals.update({f"previous_{key}": value for key, value in before.items()})
    return totals


def category_spending(db, month):
    validate_month(month)
    return _rows(db.execute("""
        SELECT c.name AS category_name,SUM(t.amount_cents) AS amount_cents
        FROM transactions t JOIN categories c ON c.id=t.category_id
        WHERE t.type='despesa' AND substr(t.date,1,7)=?
        GROUP BY c.id ORDER BY amount_cents DESC,c.name
    """, (month,)))


def daily_spending(db, month):
    validate_month(month)
    amounts = {row["date"]: row["total"] for row in db.execute("""
        SELECT date,SUM(amount_cents) AS total FROM transactions
        WHERE type='despesa' AND substr(date,1,7)=? GROUP BY date
    """, (month,))}
    year, month_number = map(int, month.split("-"))
    return [{"date": f"{month}-{day:02d}", "amount_cents": amounts.get(f"{month}-{day:02d}", 0)}
            for day in range(1, calendar.monthrange(year, month_number)[1] + 1)]


def annual_summary(db, year):
    if isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999:
        raise ValueError("Ano inválido.")
    return [{"month": f"{year:04d}-{month:02d}", **_totals(db, f"{year:04d}-{month:02d}")}
            for month in range(1, 13)]


def top_expenses(db, month, limit=10):
    validate_month(month)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limite inválido.")
    return _rows(db.execute(TRANSACTION_SELECT + """
        WHERE t.type='despesa' AND substr(t.date,1,7)=?
        ORDER BY t.amount_cents DESC,t.date DESC,t.id DESC LIMIT ?
    """, (month, limit)))
