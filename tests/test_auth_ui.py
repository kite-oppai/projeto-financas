from pathlib import Path

from streamlit.testing.v1 import AppTest

from services import auth
from tests.ui_helpers import TEST_PASSWORD, login
from ui import auth as auth_ui

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_no_navigation_no_database_and_no_exports_before_login(tmp_path, monkeypatch):
    database = tmp_path / "private.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(database))
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert not app.radio and not app.metric and not app.get("download_button")
    assert not database.exists()
    app.text_input(key="login_password").set_value("incorreta")
    next(button for button in app.button if button.label == "Entrar").click().run()
    assert any("Senha incorreta" in e.value for e in app.error)
    assert not database.exists() and not app.radio
    app.text_input(key="login_password").set_value(TEST_PASSWORD)
    next(button for button in app.button if button.label == "Entrar").click().run()
    assert app.radio and database.exists()
    app.radio(key="navigation").set_value("Movimentos").run()
    app.radio(key="movements_section").set_value("Importar e exportar").run()
    next(b for b in app.button if b.label == "Preparar arquivos para download").click().run()
    assert len(app.get("download_button")) == 2
    app.button(key="logout").click().run()
    assert not app.exception and not app.radio and not app.get("download_button")
    assert "_exports" not in app.session_state


def test_missing_hash_blocks_even_existing_session(tmp_path, monkeypatch):
    database = tmp_path / "private.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(database))
    app = login(AppTest.from_file(APP))
    monkeypatch.setattr(auth, "SECRETS_PATH", tmp_path / "absent.toml")
    app.run()
    assert not app.exception and not app.radio and not app.metric
    assert "_auth_token" not in app.session_state
    assert app.error


def test_expired_session_and_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCAS_DB_PATH", str(tmp_path / "private.db"))
    app = login(AppTest.from_file(APP))
    app.session_state["_auth_last_seen"] = -100000
    app.run()
    assert not app.radio
    for _ in range(5):
        auth_ui.LOGIN_LIMITER.failure()
    app.text_input(key="login_password").set_value(TEST_PASSWORD)
    next(b for b in app.button if b.label == "Entrar").click().run()
    assert not app.radio
    assert any("Muitas tentativas" in e.value for e in app.error)
