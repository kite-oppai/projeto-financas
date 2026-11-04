from tests.ui_helpers import login
"""O período da navegação precisa definir a data do novo lançamento."""
from datetime import date
from streamlit.testing.v1 import AppTest
from database.core import get_connection, initialize
from services.finance import create_account


def test_switching_month_and_year_resets_new_transaction_date(tmp_path, monkeypatch):
    path = tmp_path / 'period.db'
    monkeypatch.setenv('FINANCAS_DB_PATH', str(path))
    db = get_connection()
    try:
        initialize(db)
        create_account(db, 'Conta para teste de período', 'corrente')
    finally:
        db.close()
    at = login(AppTest.from_file('app.py', default_timeout=15))
    at.sidebar.radio[0].set_value('Lançamentos').run()
    # Um rascunho em outra data também não deve manter a data ao trocar o período.
    at.date_input(key='new_tx_date').set_value(date(2024, 7, 12)).run()
    at.sidebar.selectbox(key='selected_month').set_value(2).run()
    at.sidebar.number_input(key='selected_year').set_value(2025).run()
    assert not at.exception
    assert at.date_input(key='new_tx_date').value == date(2025, 2, 1)
    at.text_input(key='new_tx_description').set_value('Lançamento no mês escolhido')
    at.text_input(key='new_tx_amount').set_value('25,99')
    next(b for b in at.button if b.label == 'Cadastrar lançamento').click().run()
    assert not at.exception
    assert not at.error
    db = get_connection()
    try:
        row = db.execute('SELECT date, amount_cents FROM transactions').fetchone()
        assert row['date'] == '2025-02-01'
        assert row['amount_cents'] == 2599
    finally:
        db.close()
