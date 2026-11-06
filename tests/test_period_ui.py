"""O período da navegação precisa definir a data do novo lançamento."""
from contextlib import closing
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from database.core import get_connection, initialize
from services.finance import create_account
from tests.test_ui import click, navigate
from tests.ui_helpers import login

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_switching_month_and_year_resets_new_transaction_date(tmp_path, monkeypatch):
    path = tmp_path / "period.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    with closing(get_connection(path)) as db:
        initialize(db)
        create_account(db, "Conta para teste de período", "corrente")
    app = login(AppTest.from_file(APP, default_timeout=15))
    navigate(app, "Movimentos", "movements_section", "Lançamentos")
    click(app, "+ Novo lançamento")
    assert app.date_input(key="new_tx_date").value == date.today()
    app.date_input(key="new_tx_date").set_value(date(2024, 7, 12)).run()
    click(app, "Cancelar")
    assert "_transaction_dialog" not in app.session_state
    assert "new_tx_date" not in app.session_state
    # O AppTest 1.50 retém nós de diálogos fechados. A nova sessão evita
    # serializar esses nós; a troca de período e o cadastro são reais.
    app = login(AppTest.from_file(APP, default_timeout=15))
    app.selectbox(key="selected_month").set_value(2).run()
    app.number_input(key="selected_year").set_value(2025).run()
    click(app, "+ Novo lançamento")
    assert app.date_input(key="new_tx_date").value == date(2025, 2, 1)
    app.text_input(key="new_tx_description").set_value("Lançamento no mês escolhido")
    app.text_input(key="new_tx_amount").set_value("25,99")
    click(app, "Cadastrar lançamento")
    assert not app.error
    with closing(get_connection(path)) as db:
        row = db.execute("SELECT date, amount_cents FROM transactions").fetchone()
        assert row["date"] == "2025-02-01"
        assert row["amount_cents"] == 2599
