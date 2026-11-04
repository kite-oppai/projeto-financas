"""Metas de economia com aportes manuais, independentes dos saldos das contas."""
from services.money import clean_text, require_cents, validate_date


def _goal(db, goal_id):
    row = db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if row is None:
        raise ValueError("Meta não encontrada.")
    return dict(row)


def list_goals(db):
    rows = db.execute("""
        SELECT g.*, COALESCE(SUM(c.amount_cents), 0) AS saved_cents
        FROM goals g LEFT JOIN goal_contributions c ON c.goal_id = g.id
        GROUP BY g.id ORDER BY g.deadline, g.id
    """).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["remaining_cents"] = max(0, item["target_cents"] - item["saved_cents"])
        item["progress_percent"] = min(100, item["saved_cents"] * 100 // item["target_cents"])
        result.append(item)
    return result


def create_goal(db, name, target_cents, deadline):
    values = (clean_text(name, "Nome"), require_cents(target_cents), validate_date(deadline))
    with db:
        return db.execute("INSERT INTO goals(name,target_cents,deadline) VALUES (?,?,?)", values).lastrowid


def update_goal(db, id, name, target_cents, deadline):
    _goal(db, id)
    values = (clean_text(name, "Nome"), require_cents(target_cents), validate_date(deadline), id)
    with db:
        db.execute("UPDATE goals SET name=?,target_cents=?,deadline=? WHERE id=?", values)


def delete_goal(db, id):
    _goal(db, id)
    with db:
        db.execute("DELETE FROM goals WHERE id=?", (id,))


def list_contributions(db, goal_id):
    _goal(db, goal_id)
    return [dict(row) for row in db.execute(
        "SELECT * FROM goal_contributions WHERE goal_id=? ORDER BY date DESC,id DESC", (goal_id,)
    )]


def add_contribution(db, goal_id, date, amount_cents, notes=""):
    _goal(db, goal_id)
    if not isinstance(notes, str) or len(notes) > 5000:
        raise ValueError("A observação deve ter no máximo 5.000 caracteres.")
    values = (goal_id, validate_date(date), require_cents(amount_cents), notes.strip())
    with db:
        return db.execute(
            "INSERT INTO goal_contributions(goal_id,date,amount_cents,notes) VALUES (?,?,?,?)", values
        ).lastrowid


def delete_contribution(db, id):
    if db.execute("SELECT id FROM goal_contributions WHERE id=?", (id,)).fetchone() is None:
        raise ValueError("Aporte não encontrado.")
    with db:
        db.execute("DELETE FROM goal_contributions WHERE id=?", (id,))
