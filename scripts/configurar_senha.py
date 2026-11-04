"""Configura uma senha por entrada oculta; salva somente o hash bcrypt."""
import getpass
from pathlib import Path
import sys
import tempfile
import os

# Permite executar `python scripts/configurar_senha.py` a partir da raiz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import toml
from services.auth import SECRETS_PATH, hash_password


def save_password(password, confirmation, path=SECRETS_PATH):
    if password != confirmation:
        raise ValueError("As senhas não coincidem. Nada foi alterado.")
    hashed = hash_password(password)
    target = Path(path)
    data = toml.load(target) if target.exists() else {}
    if not isinstance(data.get("auth", {}), dict):
        raise ValueError("A seção auth do arquivo secrets.toml é inválida.")
    data.setdefault("auth", {})["password_hash"] = hashed
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".senha-", suffix=".tmp", delete=False) as output:
            temp_name = output.name
            output.write(toml.dumps(data))
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def main():
    if not sys.stdin.isatty():
        print("Execute este comando em um terminal interativo do PC para digitar a senha sem exibi-la.", file=sys.stderr)
        return 1
    print("Será salvo somente o hash bcrypt em .streamlit/secrets.toml, fora do Git.")
    print("Se já existir senha, ela será substituída e as sessões antigas perderão acesso na próxima interação.")
    try:
        if SECRETS_PATH.exists() and input("Substituir a senha atual? Digite SIM: ").strip() != "SIM":
            print("Operação cancelada.")
            return
        password = getpass.getpass("Nova senha (mínimo 12 caracteres): ")
        confirmation = getpass.getpass("Repita a senha: ")
        save_password(password, confirmation)
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f"Não foi possível configurar a senha: {exc}", file=sys.stderr)
        return 1
    print("Senha configurada. Guarde-a em um local seguro. Nenhum dado financeiro foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
