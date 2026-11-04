import sqlite3
import sys

from database.core import get_connection, initialize
from services import auth, launcher


def test_launcher_backs_up_before_server_accepts_connections(tmp_path, monkeypatch):
    path = tmp_path / "financas.db"
    db = get_connection(path)
    initialize(db)
    with db:
        db.execute("INSERT INTO accounts(name,kind,initial_balance_cents) VALUES ('Minha conta','corrente',12345)")
    db.close()
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    monkeypatch.setattr(sys, "argv", ["launcher", "--server.address", "127.0.0.1"])
    from streamlit.web import cli
    calls = []

    def start_server():
        backups = list((tmp_path / "backups").glob("*.db"))
        assert len(backups) == 1
        copy = sqlite3.connect(backups[0])
        try:
            assert copy.execute("SELECT initial_balance_cents FROM accounts").fetchone()[0] == 12345
        finally:
            copy.close()
        assert sys.argv == ["streamlit", "run", "app.py", "--server.address", "127.0.0.1"]
        calls.append(True)
    monkeypatch.setattr(cli, "main", start_server)
    assert launcher.main() == 0
    assert calls == [True]


def test_launcher_refuses_missing_password_before_creating_database(tmp_path, monkeypatch):
    path = tmp_path / "not-created.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    monkeypatch.setattr(auth, "SECRETS_PATH", tmp_path / "absent.toml")
    from streamlit.web import cli
    monkeypatch.setattr(cli, "main", lambda: (_ for _ in ()).throw(AssertionError("Servidor não deve iniciar")))
    assert launcher.main() == 1
    assert not path.exists()


def test_corrupted_database_blocks_server_without_replacing_source(tmp_path, monkeypatch):
    path = tmp_path / "broken.db"
    path.write_bytes(b"arquivo corrompido para teste")
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    from streamlit.web import cli
    monkeypatch.setattr(cli, "main", lambda: (_ for _ in ()).throw(AssertionError("Servidor não deve iniciar")))
    assert launcher.main() == 1
    assert path.read_bytes() == b"arquivo corrompido para teste"
