from pathlib import Path

import pytest
import toml

from scripts.configurar_senha import save_password
from services.auth import (LoginLimiter, SESSION_TIMEOUT, authenticated, hash_password,
                           load_password_hash, sign_in, validate_hash, verify_password)


def test_password_hash_checks_exact_password_and_bcrypt_length():
    hashed = hash_password("uma-senha-segura-123")
    assert hashed.startswith("$2b$12$")
    assert verify_password("uma-senha-segura-123", hashed)
    assert not verify_password("senha errada", hashed)
    assert not verify_password("á" * 37, hashed)
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("á" * 37)
    with pytest.raises(ValueError, match="12 caracteres"):
        hash_password("curta")


@pytest.mark.parametrize("value", [None, 123, [], "texto", "$2b$04$" + "a" * 53, "$2b$31$" + "a" * 53])
def test_invalid_configuration_fails_closed(value):
    with pytest.raises(ValueError):
        validate_hash(value)


def test_load_requires_valid_secret(tmp_path):
    path = tmp_path / "missing.toml"
    with pytest.raises(ValueError):
        load_password_hash(path)
    path.write_text("[auth]\npassword_hash = [\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_password_hash(path)


def test_configure_saves_only_hash_and_preserves_other_settings(tmp_path):
    path = tmp_path / "secrets.toml"
    path.write_text('[other]\nsetting="preservar"\n', encoding="utf-8")
    password = "senha-nova-segura-123"
    save_password(password, password, path)
    assert password not in path.read_text()
    assert toml.load(path)["other"]["setting"] == "preservar"
    assert verify_password(password, load_password_hash(path))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="coincidem"):
        save_password(password, "outra", path)
    assert path.read_bytes() == before


def test_sessions_expire_and_password_rotation_invalidates_session(test_password_hash):
    state = {"_exports": {"csv": b"dados privados"}}
    sign_in(state, test_password_hash, now=100)
    assert "_exports" not in state
    assert authenticated(state, test_password_hash, now=101)
    assert not authenticated(state, test_password_hash, now=101 + SESSION_TIMEOUT)
    sign_in(state, test_password_hash, now=200)
    assert not authenticated(state, "$2b$12$" + "x" * 53, now=201)
    assert not authenticated(state, test_password_hash, now=199)


def test_limiter_blocks_after_five_failures_and_recovers():
    limiter = LoginLimiter()
    for _ in range(5):
        assert limiter.remaining(now=100) == 0
        limiter.failure(now=100)
    assert limiter.remaining(now=100) > 0
    assert limiter.remaining(now=159) > 0
    assert limiter.remaining(now=160) == 0
