import hashlib
from datetime import date

import pytest

from database.core import get_connection, initialize
from services.finance import budget_status
from seed import seed_demo


def test_demo_is_repeatable_and_has_examples(tmp_path):
    path = tmp_path / "demo.db"
    assert seed_demo(path, today=date(2026, 1, 31))
    before = path.read_bytes()
    assert not seed_demo(path, today=date(2026, 2, 1))
    assert path.read_bytes() == before
    db = get_connection(path)
    try:
        assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 27
        assert db.execute("SELECT count(*) FROM budgets").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM goal_contributions").fetchone()[0] == 1
        assert db.execute("SELECT min(date) FROM transactions").fetchone()[0] == "2025-11-05"
        assert db.execute("SELECT start_month FROM recurring_rules").fetchone()[0] == "2026-02"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert {row["status"] for row in budget_status(db, "2026-01")} == {
            "normal", "atencao", "excedido"
        }
    finally:
        db.close()


def test_refuses_existing_real_database_without_changing_it(tmp_path):
    path = tmp_path / "real.db"
    db = get_connection(path)
    initialize(db)
    with db:
        db.execute("INSERT INTO accounts(name, kind) VALUES ('Minha conta', 'corrente')")
    db.close()
    before = hashlib.sha256(path.read_bytes()).digest()
    with pytest.raises(ValueError, match="não é uma base de demonstração"):
        seed_demo(path)
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_explicit_demo_does_not_touch_environment_database(tmp_path, monkeypatch):
    personal = tmp_path / "personal.db"
    personal.write_bytes(b"nao modificar")
    monkeypatch.setenv("FINANCAS_DB_PATH", str(personal))
    assert seed_demo(tmp_path / "demo.db", today=date(2026, 1, 1))
    assert personal.read_bytes() == b"nao modificar"


def test_non_sqlite_file_is_preserved(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"meus dados")
    with pytest.raises(ValueError):
        seed_demo(path)
    assert path.read_bytes() == b"meus dados"
