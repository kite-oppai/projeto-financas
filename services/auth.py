"""Senha única local, somente hash bcrypt; nenhuma senha em arquivo ou log."""
from collections import deque
import hashlib
from functools import lru_cache
from pathlib import Path
import re
import threading
import time
import tomllib

import bcrypt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / ".streamlit" / "secrets.toml"
SESSION_TIMEOUT = 30 * 60
_HASH_PATTERN = re.compile(r"^\$2[aby]\$(\d{2})\$[./A-Za-z0-9]{53}$")


def validate_hash(value):
    match = _HASH_PATTERN.fullmatch(value) if isinstance(value, str) else None
    if not match or not 10 <= int(match[1]) <= 14:
        raise ValueError("Hash de senha inválido. Execute scripts/configurar_senha.py novamente.")
    return _check_hash(value)


@lru_cache(maxsize=16)
def _check_hash(value):
    try:
        # Valida também o salt bcrypt, sem executar trabalho proporcional à senha.
        bcrypt.checkpw(b"", value.encode("ascii"))
    except ValueError as exc:
        raise ValueError("Hash de senha inválido. Configure a senha novamente.") from exc
    return value


def load_password_hash(path=None):
    target = Path(path) if path is not None else SECRETS_PATH
    try:
        with target.open("rb") as source:
            data = tomllib.load(source)
        value = data.get("auth", {}).get("password_hash")
    except (OSError, tomllib.TOMLDecodeError, AttributeError) as exc:
        raise ValueError("Configure a senha no PC com scripts/configurar_senha.py antes de abrir o app.") from exc
    return validate_hash(value)


def hash_password(password):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Use uma senha com pelo menos 12 caracteres.")
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raise ValueError("A senha deve ter no máximo 72 bytes em UTF-8 (acentos ocupam mais de um byte).")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password, password_hash):
    if not isinstance(password, str) or not password or len(password.encode("utf-8")) > 72:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, UnicodeError, AttributeError):
        return False


def session_token(password_hash):
    return hashlib.sha256(password_hash.encode("ascii")).hexdigest()


def authenticated(state, password_hash, now=None):
    """Expiração por inatividade, verificada antes de cada ação/execução da página."""
    now = time.monotonic() if now is None else now
    last = state.get("_auth_last_seen")
    valid = (state.get("_auth_token") == session_token(password_hash)
             and isinstance(last, (int, float)) and 0 <= now - last < SESSION_TIMEOUT)
    if valid:
        state["_auth_last_seen"] = now
    return valid


def sign_in(state, password_hash, now=None):
    state.clear()
    state["_auth_token"] = session_token(password_hash)
    state["_auth_last_seen"] = time.monotonic() if now is None else now


class LoginLimiter:
    """Cinco falhas por minuto, compartilhadas entre sessões deste processo."""
    def __init__(self, limit=5, window=60):
        self.limit, self.window = limit, window
        self.failures = deque()
        self.lock = threading.Lock()

    def _prune(self, now):
        while self.failures and now - self.failures[0] >= self.window:
            self.failures.popleft()

    def remaining(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self._prune(now)
            return max(1, int(self.window - (now - self.failures[0])) + 1) if len(self.failures) >= self.limit else 0

    def failure(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self._prune(now)
            self.failures.append(now)


LOGIN_LIMITER = LoginLimiter()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verifica se existe uma senha bcrypt configurada.")
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        load_password_hash()
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print("Senha configurada. Nenhum segredo foi exibido.")


if __name__ == "__main__":
    main()
