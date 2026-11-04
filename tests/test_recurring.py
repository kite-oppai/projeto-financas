from datetime import date
import pytest
from services.finance import create_account, delete_transaction
from services.recurring import create_rule, delete_rule, generate_due, list_rules, update_rule


@pytest.fixture
def refs(db):
    return db.execute("SELECT id FROM categories ORDER BY id").fetchone()[0], create_account(db, "Banco", "corrente")


def rule(db, refs, **kwargs):
    values = dict(description="Aluguel", amount_cents=150000, type="despesa", category_id=refs[0],
                  account_id=refs[1], day=31, start_month="2024-01")
    values.update(kwargs)
    return create_rule(db, **values)


def test_catchup_clamps_february_and_is_idempotent(db, refs):
    id = rule(db, refs)
    assert generate_due(db, date(2024, 3, 30)) == 2
    assert [r[0] for r in db.execute("SELECT date FROM transactions ORDER BY date")] == ["2024-01-31", "2024-02-29"]
    assert generate_due(db, "2024-03-30") == 0
    assert generate_due(db, "2024-03-31") == 1
    assert len(list_rules(db)) == 1


def test_deleting_generated_transaction_does_not_regenerate(db, refs):
    rule(db, refs, start_month="2024-02", end_month="2024-02")
    assert generate_due(db, "2024-03-31") == 1
    id = db.execute("SELECT id FROM transactions").fetchone()[0]
    delete_transaction(db, id)
    assert generate_due(db, "2024-03-31") == 0


def test_inactive_end_month_and_deleting_rule_preserve_history(db, refs):
    id = rule(db, refs, active=False, end_month="2024-02")
    assert generate_due(db, "2024-04-30") == 0
    update_rule(db, id, "Aluguel novo", 160000, "despesa", refs[0], refs[1], 31,
                "2024-01", "2024-02", active=True)
    assert generate_due(db, "2024-04-30") == 2
    delete_rule(db, id)
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
    assert db.execute("SELECT recurrence_id FROM transactions LIMIT 1").fetchone()[0] is None
    assert db.execute("SELECT COUNT(*) FROM recurrence_runs").fetchone()[0] == 0


def test_edits_apply_only_to_pending_months(db, refs):
    id = rule(db, refs, day=5)
    assert generate_due(db, "2024-01-05") == 1
    update_rule(db, id, "Aluguel reajustado", 200000, "despesa", refs[0], refs[1], 5, "2024-01")
    assert generate_due(db, "2024-02-05") == 1
    assert [r[0] for r in db.execute("SELECT amount_cents FROM transactions ORDER BY date")] == [150000, 200000]


@pytest.mark.parametrize("overrides", [{"day":0}, {"day":32}, {"day":True}, {"amount_cents":1.2},
                                        {"amount_cents":0}, {"end_month":"2023-12"}, {"account_id":999},
                                        {"type":"inválido"}, {"start_month":"2024-13"}])
def test_rule_validation(db, refs, overrides):
    with pytest.raises(ValueError):
        rule(db, refs, **overrides)
    assert list_rules(db) == []


def test_two_sessions_generate_one_occurrence_per_month(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from database.core import get_connection, initialize
    path = tmp_path / "sessions.db"
    db = get_connection(path)
    initialize(db)
    refs = (db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0], create_account(db, "Banco", "corrente"))
    rule(db, refs)
    db.close()
    ready = Barrier(2)

    def run():
        conn = get_connection(path)
        try:
            ready.wait(timeout=5)
            return generate_due(conn, "2024-03-31")
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: run(), range(2)))
    assert sum(counts) == 3
    db = get_connection(path)
    try:
        assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM recurrence_runs").fetchone()[0] == 3
    finally:
        db.close()


def test_rule_notes_are_validated(db, refs):
    for notes in (123, "x" * 5001):
        with pytest.raises(ValueError, match="observação"):
            rule(db, refs, notes=notes)
