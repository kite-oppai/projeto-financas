"""Inicializa no mesmo processo: senha válida, backup e servidor Streamlit."""
import os
import sys

from database.core import DEFAULT_DB
from services.auth import PROJECT_ROOT, load_password_hash
from services.backup import backup_once


def main():
    os.chdir(PROJECT_ROOT)
    try:
        load_password_hash()
        backup = backup_once(os.environ.get("FINANCAS_DB_PATH", DEFAULT_DB))
        print("Backup de inicialização concluído." if backup else
              "Banco ainda não existe; será criado após o primeiro login.", flush=True)
    except (OSError, ValueError) as exc:
        print(f"Não foi possível iniciar: {exc}", file=sys.stderr)
        return 1
    from streamlit.web import cli
    sys.argv = ["streamlit", "run", "app.py", *sys.argv[1:]]
    cli.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
