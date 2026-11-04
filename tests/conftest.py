import pytest

from database.core import get_connection, initialize
import bcrypt

from services import auth
from tests.ui_helpers import TEST_PASSWORD


@pytest.fixture(scope="session")
def test_password_hash():
    return bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode()


@pytest.fixture(autouse=True)
def temporary_auth_config(tmp_path, monkeypatch, test_password_hash):
    """Configuração real de teste isolada, sem criar secrets.toml do usuário."""
    secret = tmp_path / "secrets.toml"
    secret.write_text('[auth]\npassword_hash = "' + test_password_hash + '"\n', encoding="utf-8")
    monkeypatch.setattr(auth, "SECRETS_PATH", secret)
    from ui import auth as auth_ui
    monkeypatch.setattr(auth_ui, "LOGIN_LIMITER", auth.LoginLimiter())


@pytest.fixture
def db():
    conn = get_connection(":memory:")
    initialize(conn)
    yield conn
    conn.close()
