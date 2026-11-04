"""Cópias consistentes do SQLite, sem depender de copiar um banco em uso."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import uuid


_once_lock = threading.Lock()
_completed = {}
_BACKUP_TIMEOUT_SECONDS = 30


def _source_path(path):
    return Path(path).expanduser().resolve()


def _prefix(source):
    # Bancos homônimos em pastas diferentes não compartilham a retenção.
    identity = os.path.normcase(str(source))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    name = re.sub(r"[^\w.-]", "_", source.stem)[:50] or "banco"
    return f"{name}-{digest}-"


def backup_database(path, keep=7, backup_dir=None):
    """Cria uma cópia e mantém as últimas ``keep`` cópias deste banco.

    Um banco inexistente não é criado. A origem é aberta somente para leitura;
    falhas na cópia ou validação preservam os backups anteriores. Não inclui
    arquivos de senha: a cópia contém somente o banco financeiro.
    """
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
        raise ValueError("A retenção de backups deve ser um inteiro maior que zero.")
    if str(path) == ":memory:":
        return None
    source = _source_path(path)
    if not source.exists():
        return None
    if not source.is_file():
        raise ValueError("O caminho do banco deve apontar para um arquivo.")
    destination_dir = (_source_path(backup_dir) if backup_dir is not None
                       else source.parent / "backups")
    prefix = _prefix(source)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = destination_dir / f"{prefix}{stamp}-{uuid.uuid4().hex}.db"
    temporary = None
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{prefix}", suffix=".tmp", dir=destination_dir)
        os.close(descriptor)
        temporary = Path(temporary_name)
        deadline = time.monotonic() + _BACKUP_TIMEOUT_SECONDS

        def check_progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise ValueError("O banco está ocupado. Tente iniciar o aplicativo novamente.")

        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=15)) as original:
            with closing(sqlite3.connect(temporary)) as copy:
                original.backup(copy, pages=128, progress=check_progress, sleep=0.1)
                result = copy.execute("PRAGMA quick_check").fetchall()
                if result != [("ok",)]:
                    raise ValueError("A verificação de integridade do backup falhou.")
        # UUID evita reutilizar nomes. Uma eventual colisão nunca substitui um backup.
        if destination.exists():
            raise ValueError("Não foi possível criar um nome exclusivo para o backup.")
        os.replace(temporary, destination)
        temporary = None
    except (OSError, sqlite3.Error) as exc:
        raise ValueError(
            "Não foi possível criar o backup. Verifique o espaço em disco e as permissões. "
            "O banco original e as cópias anteriores foram preservados."
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    try:
        # Retenção só ocorre após publicar uma cópia completa e validada.
        owned_name = re.compile(re.escape(prefix) + r"\d{8}T\d{12}Z-[0-9a-f]{32}\.db$")
        previous = [p for p in destination_dir.glob(f"{prefix}*.db")
                    if p != destination and owned_name.fullmatch(p.name)]
        # A cópia recém-criada é mantida mesmo após ajuste regressivo do relógio.
        copies = [destination, *sorted(previous, key=lambda p: p.name, reverse=True)]
        for obsolete in copies[keep:]:
            obsolete.unlink()
    except OSError as exc:
        raise ValueError(
            "Backup criado, mas não foi possível remover cópias antigas. "
            "Verifique as permissões da pasta de backups."
        ) from exc
    return destination


def backup_once(path, keep=7, backup_dir=None):
    """Uma cópia por banco/processo, inclusive entre reruns e sessões Streamlit."""
    if str(path) == ":memory:":
        return None
    source = _source_path(path)
    with _once_lock:
        if source in _completed:
            return _completed[source]
        result = backup_database(source, keep=keep, backup_dir=backup_dir)
        if result is not None:
            _completed[source] = result
        return result
