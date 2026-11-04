from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3

import pytest

from database.core import get_connection, initialize
from services.backup import backup_database, backup_once


def create_db(path, balance=123456):
    with closing(get_connection(path)) as db:
        initialize(db)
        with db:
            db.execute("INSERT INTO accounts(name,kind,initial_balance_cents) VALUES (?,?,?)",
                       ("Conta", "corrente", balance))


def saved_balance(path):
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        return db.execute("SELECT initial_balance_cents FROM accounts").fetchone()[0]


def test_complete_backup_preserves_schema_values_and_source(tmp_path):
    source = tmp_path / "financas.db"
    create_db(source)
    before = source.read_bytes()
    copy = backup_database(source)
    assert copy.parent == tmp_path / "backups"
    assert saved_balance(copy) == 123456
    assert source.read_bytes() == before
    with closing(sqlite3.connect(copy)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM categories").fetchone()[0] == 8
    assert not list(copy.parent.glob("*.tmp"))


def test_reads_committed_wal_content_without_copying_wal_files(tmp_path):
    source = tmp_path / "wal.db"
    create_db(source)
    with closing(sqlite3.connect(source)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        with db:
            db.execute("UPDATE accounts SET initial_balance_cents=999999")
        assert source.with_name("wal.db-wal").exists()
        copy = backup_database(source)
        assert saved_balance(copy) == 999999


def test_retention_separate_for_each_source_even_same_basename(tmp_path):
    first = tmp_path / "personal" / "financas.db"
    second = tmp_path / "demo" / "financas.db"
    create_db(first)
    create_db(second, balance=500)
    folder = tmp_path / "copies"
    first_copies = [backup_database(first, backup_dir=folder) for _ in range(9)]
    second_copy = backup_database(second, backup_dir=folder)
    assert not first_copies[0].exists() and not first_copies[1].exists()
    assert all(path.exists() for path in first_copies[2:])
    assert second_copy.exists() and saved_balance(second_copy) == 500
    assert len(list(folder.glob("*.db"))) == 8


def test_once_keeps_original_startup_snapshot_across_calls_and_threads(tmp_path):
    source = tmp_path / "once.db"
    create_db(source, balance=100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: backup_once(source), range(8)))
    assert len(set(results)) == 1
    with closing(sqlite3.connect(source)) as db:
        with db:
            db.execute("UPDATE accounts SET initial_balance_cents=200")
    assert backup_once(source) == results[0]
    assert saved_balance(results[0]) == 100
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_missing_source_is_not_created_or_cached(tmp_path):
    source = tmp_path / "new.db"
    assert backup_database(source) is None
    assert backup_once(source) is None
    assert not source.exists()
    assert not (tmp_path / "backups").exists()
    create_db(source)
    assert backup_once(source).exists()
    assert backup_database(":memory:") is None


def test_corruption_preserves_original_and_old_copies(tmp_path):
    source = tmp_path / "financas.db"
    create_db(source)
    old = backup_database(source, keep=1)
    old_bytes = old.read_bytes()
    source.write_bytes(b"arquivo corrompido")
    with pytest.raises(ValueError, match="backup"):
        backup_database(source, keep=1)
    assert source.read_bytes() == b"arquivo corrompido"
    assert old.read_bytes() == old_bytes
    assert list(old.parent.glob("*.db")) == [old]
    assert not list(old.parent.glob("*.tmp"))


def test_destination_failure_does_not_change_source(tmp_path):
    source = tmp_path / "financas.db"
    create_db(source)
    before = source.read_bytes()
    not_directory = tmp_path / "arquivo"
    not_directory.write_text("não substituir")
    with pytest.raises(ValueError, match="backup"):
        backup_database(source, backup_dir=not_directory)
    assert source.read_bytes() == before
    assert not_directory.read_text() == "não substituir"


@pytest.mark.parametrize("keep", [0, -1, True, 1.2, "7"])
def test_invalid_retention(tmp_path, keep):
    with pytest.raises(ValueError, match="retenção"):
        backup_database(tmp_path / "db.db", keep=keep)
