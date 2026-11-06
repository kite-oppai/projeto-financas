"""Exercita a prévia na interface; somente o seletor de arquivo é substituído.

AppTest não expõe upload de arquivos. Os bytes abaixo passam pelo leitor,
mapeamento, validação e confirmação reais do aplicativo.
"""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import streamlit as st
from streamlit.testing.v1 import AppTest

from database.core import get_connection, initialize
from services.finance import create_account, list_transactions
from tests.ui_helpers import login


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def start_import(tmp_path, monkeypatch, content):
    path = tmp_path / "import.db"
    with closing(get_connection(path)) as db:
        initialize(db)
        create_account(db, "Banco", "corrente")
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    upload = SimpleNamespace(name="extrato.csv", getvalue=lambda: content)
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: upload)
    app = login(AppTest.from_file(APP, default_timeout=15))
    app.radio(key="navigation").set_value("Movimentos").run()
    app.radio(key="movements_section").set_value("Importar e exportar").run()
    assert not app.exception
    return app, path


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_csv_preview_confirmation_duplicate_and_encoding_change(tmp_path, monkeypatch):
    content = "Data;Descricao;Valor\n01/11/2026;Café;-10,01\n".encode()
    app, path = start_import(tmp_path, monkeypatch, content)
    assert not any(b.label == "Salvar importação" for b in app.button)
    click(app, "Gerar prévia")
    assert next(b for b in app.button if b.label == "Salvar importação").disabled
    app.checkbox(key="import_include_duplicates").check().run()
    click(app, "Gerar prévia")
    assert not app.checkbox(key="import_include_duplicates").value
    # Trocar a codificação altera o conteúdo lido e invalida a prévia antiga.
    app.selectbox(key="csv_encoding").set_value("cp1252").run()
    assert not any(b.label == "Salvar importação" for b in app.button)
    app.selectbox(key="csv_encoding").set_value("utf-8-sig").run()
    click(app, "Gerar prévia")
    next(c for c in app.checkbox if c.label.startswith("Conferi")).check().run()
    click(app, "Salvar importação")
    with closing(get_connection(path)) as db:
        rows = list_transactions(db)
        assert len(rows) == 1
        assert rows[0]["description"] == "Café" and rows[0]["amount_cents"] == 1001
    assert "_import_preview" not in app.session_state
    # AppTest 1.50 conserva widgets removidos após um rerun interno. Reabra
    # a interface autenticada para verificar duplicatas contra o banco real.
    app = login(AppTest.from_file(APP, default_timeout=15))
    app.radio(key="navigation").set_value("Movimentos").run()
    app.radio(key="movements_section").set_value("Importar e exportar").run()
    click(app, "Gerar prévia")
    assert any("1 possíveis duplicatas" in text.value for text in app.markdown)
    next(c for c in app.checkbox if c.label.startswith("Conferi")).check().run()
    click(app, "Salvar importação")
    with closing(get_connection(path)) as db:
        assert len(list_transactions(db)) == 1


def test_invalid_preview_blocks_save_but_keeps_export_available(tmp_path, monkeypatch):
    app, path = start_import(tmp_path, monkeypatch,
                            b"Data;Descricao;Valor\n31/02/2026;Compra;10,00\n")
    click(app, "Gerar prévia")
    assert app.error
    next(c for c in app.checkbox if c.label.startswith("Conferi")).check().run()
    assert next(b for b in app.button if b.label == "Salvar importação").disabled
    click(app, "Preparar arquivos para download")
    assert len(app.get("download_button")) == 2
    with closing(get_connection(path)) as db:
        assert not list_transactions(db)
