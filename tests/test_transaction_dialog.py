"""Cadastros em diálogo mantêm precisão, cancelamento e acesso autenticado."""
from contextlib import closing
from datetime import date

from streamlit.testing.v1 import AppTest

from database.core import get_connection, initialize
from services.finance import create_account, create_transaction, list_transactions
from tests.ui_helpers import login


HARNESS = """
from contextlib import closing
import streamlit as st
from database.core import get_connection
from ui.auth import require_login
from ui.transactions import render
require_login()
with closing(get_connection()) as db:
    render(db, '2026-01')
"""


def prepared_app(tmp_path, monkeypatch):
    path = tmp_path / 'dialogs.db'
    monkeypatch.setenv('FINANCAS_DB_PATH', str(path))
    with closing(get_connection(path)) as db:
        initialize(db)
        account = create_account(db, 'Principal', 'corrente', 10000)
        category = db.execute('SELECT id FROM categories ORDER BY id').fetchone()[0]
    app = login(AppTest.from_string(HARNESS, default_timeout=15))
    return app, path, account, category


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_new_dialog_saves_exact_cents_after_parent_connection_closed(tmp_path, monkeypatch):
    app, path, _, _ = prepared_app(tmp_path, monkeypatch)
    assert not app.text_input(key='transaction_search').value
    assert not any(element.key == 'new_tx_description' for element in app.text_input)
    click(app, '+ Novo lançamento')
    assert app.date_input(key='new_tx_date').value == date(2026, 1, 1)
    app.text_input(key='new_tx_description').set_value('Café do mês escolhido')
    app.text_input(key='new_tx_amount').set_value('10,01')
    click(app, 'Cadastrar lançamento')
    with closing(get_connection(path)) as db:
        rows = list_transactions(db, '2026-01')
        assert len(rows) == 1
        assert rows[0]['amount_cents'] == 1001
        assert rows[0]['date'] == '2026-01-01'
    assert '_transaction_dialog' not in app.session_state
    # AppTest 1.50 mantém a árvore de eventos do diálogo já fechado. Uma nova
    # sessão autenticada verifica o estado após recarregar sem alterar dados.
    refreshed = login(AppTest.from_string(HARNESS, default_timeout=15))
    assert not any(element.key == 'new_tx_description' for element in refreshed.text_input)


def test_cancel_discards_draft_and_invalid_money_does_not_save(tmp_path, monkeypatch):
    app, path, _, _ = prepared_app(tmp_path, monkeypatch)
    click(app, '+ Novo lançamento')
    app.text_input(key='new_tx_description').set_value('Não salvar')
    app.text_input(key='new_tx_amount').set_value('0,001')
    click(app, 'Cadastrar lançamento')
    assert app.error
    with closing(get_connection(path)) as db:
        assert not list_transactions(db)
    click(app, 'Cancelar')
    assert '_transaction_dialog' not in app.session_state
    assert 'new_tx_description' not in app.session_state
    app = login(AppTest.from_string(HARNESS, default_timeout=15))
    click(app, '+ Novo lançamento')
    assert app.text_input(key='new_tx_description').value == ''
    assert app.text_input(key='new_tx_amount').value == '0,00'
    click(app, 'Cancelar')
    with closing(get_connection(path)) as db:
        assert not list_transactions(db)


def test_edit_and_confirmed_delete_in_dialog(tmp_path, monkeypatch):
    app, path, account, category = prepared_app(tmp_path, monkeypatch)
    with closing(get_connection(path)) as db:
        record = create_transaction(db, '2026-01-03', 'Mercado', 5000, 'despesa', category, account)
    app.run()
    click(app, 'Editar lançamento')
    app.text_input(key=f'edit_tx_{record}_amount').set_value('49,99')
    click(app, 'Salvar lançamento')
    with closing(get_connection(path)) as db:
        assert list_transactions(db)[0]['amount_cents'] == 4999
    assert '_transaction_dialog' not in app.session_state
    app = login(AppTest.from_string(HARNESS, default_timeout=15))
    click(app, 'Editar lançamento')
    assert next(button for button in app.button if button.label == 'Excluir lançamento').disabled
    app.checkbox(key=f'del_tx_{record}_confirm').check().run()
    click(app, 'Excluir lançamento')
    with closing(get_connection(path)) as db:
        assert not list_transactions(db)


def test_filter_combines_text_and_catalogs_without_changing_original_rows(tmp_path, monkeypatch):
    from ui.transactions import filter_transactions
    rows = [dict(description='Mercado', category_name='Casa', account_name='Cartão', notes='Compra mensal',
                 type='despesa', category_id=1, account_id=2, amount_cents=1001),
            dict(description='Salário', category_name='Outros', account_name='Banco', notes='',
                 type='receita', category_id=3, account_id=4, amount_cents=500000)]
    assert filter_transactions(rows, 'MENSAL', 'despesa', 1, 2) == [rows[0]]
    assert filter_transactions(rows, 'mercado', 'receita') == []
    assert filter_transactions(rows, account_id=4) == [rows[1]]
    assert rows[0]['amount_cents'] == 1001


def test_expired_session_cannot_submit_open_dialog(tmp_path, monkeypatch):
    app, path, _, _ = prepared_app(tmp_path, monkeypatch)
    click(app, '+ Novo lançamento')
    app.text_input(key='new_tx_description').set_value('Não deve gravar após expirar')
    app.text_input(key='new_tx_amount').set_value('10,01')
    app.session_state['_auth_last_seen'] = -100000
    click(app, 'Cadastrar lançamento')
    assert '_auth_token' not in app.session_state
    assert '_transaction_dialog' not in app.session_state
    with closing(get_connection(path)) as db:
        assert not list_transactions(db)
