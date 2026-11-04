"""Recorrências mensais: gera somente ocorrências vencidas e evita duplicatas."""
import calendar
from datetime import date
from services.money import validate_date, validate_month
from services.finance import transaction_values


def _values(db, description, amount_cents, type, category_id, account_id, day,
            start_month, end_month, notes, active):
    if not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 31:
        raise ValueError("Dia deve estar entre 1 e 31.")
    start_month = validate_month(start_month)
    end_month = validate_month(end_month) if end_month else None
    if end_month and end_month < start_month:
        raise ValueError("O mês final deve ser igual ou posterior ao inicial.")
    if not isinstance(active, (bool, int)) or active not in (0, 1):
        raise ValueError("Situação da recorrência inválida.")
    values = transaction_values(db, start_month + "-01", description, amount_cents, type,
                                category_id, account_id, notes)
    return (*values[1:], day, start_month, end_month, int(active))


def _rule(db, id):
    row = db.execute("SELECT * FROM recurring_rules WHERE id=?", (id,)).fetchone()
    if row is None:
        raise ValueError("Recorrência não encontrada.")
    return dict(row)


def list_rules(db):
    return [dict(row) for row in db.execute("""
        SELECT r.*, c.name AS category_name, a.name AS account_name FROM recurring_rules r
        JOIN categories c ON c.id=r.category_id JOIN accounts a ON a.id=r.account_id
        ORDER BY r.active DESC,r.description,r.id
    """)]


def create_rule(db, description, amount_cents, type, category_id, account_id, day,
                start_month, end_month=None, notes="", active=True):
    values = _values(db, description, amount_cents, type, category_id, account_id, day,
                     start_month, end_month, notes, active)
    with db:
        return db.execute("""INSERT INTO recurring_rules
            (description,amount_cents,type,category_id,account_id,notes,day,start_month,end_month,active)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", values).lastrowid


def update_rule(db, id, description, amount_cents, type, category_id, account_id, day,
                start_month, end_month=None, notes="", active=True):
    _rule(db, id)
    values = _values(db, description, amount_cents, type, category_id, account_id, day,
                     start_month, end_month, notes, active)
    with db:
        db.execute("""UPDATE recurring_rules SET description=?,amount_cents=?,type=?,category_id=?,
            account_id=?,notes=?,day=?,start_month=?,end_month=?,active=? WHERE id=?""", (*values, id))


def delete_rule(db, id):
    _rule(db, id)
    with db:
        db.execute("DELETE FROM recurring_rules WHERE id=?", (id,))


def generate_due(db, as_of=None):
    """Ao abrir o app, recupera meses pendentes até hoje; dia 31 usa o último dia."""
    cutoff = date.fromisoformat(validate_date(as_of or date.today()))
    count = 0
    with db:
        for rule in db.execute("SELECT * FROM recurring_rules WHERE active=1").fetchall():
            year, month = map(int, rule["start_month"].split("-"))
            while (year, month) <= (cutoff.year, cutoff.month):
                period = f"{year:04d}-{month:02d}"
                if rule["end_month"] and period > rule["end_month"]:
                    break
                due = date(year, month, min(rule["day"], calendar.monthrange(year, month)[1]))
                if due > cutoff:
                    break
                inserted = db.execute("""INSERT OR IGNORE INTO recurrence_runs(recurrence_id,month)
                    VALUES (?,?)""", (rule["id"], period))
                if inserted.rowcount == 1:
                    db.execute("""INSERT INTO transactions
                        (date,description,amount_cents,type,category_id,account_id,notes,recurrence_id,recurrence_month)
                        VALUES (?,?,?,?,?,?,?,?,?)""", (due.isoformat(), rule["description"], rule["amount_cents"],
                        rule["type"], rule["category_id"], rule["account_id"], rule["notes"], rule["id"], period))
                    count += 1
                month += 1
                if month == 13:
                    year, month = year + 1, 1
    return count
