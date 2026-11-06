"""Regressões da navegação compacta e revelação progressiva de dados."""
from contextlib import closing
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from database.core import get_connection, initialize
from seed import seed_demo
from services.finance import create_account, create_transaction, list_categories
from tests.test_ui import click, navigate
from tests.ui_helpers import login

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_empty_summary_guides_user_to_first_account(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCAS_DB_PATH', str(tmp_path / 'first-account.db'))
    app = login(AppTest.from_file(APP, default_timeout=15))
    click(app, 'Cadastrar primeira conta')
    assert app.radio(key='navigation').value == 'Ajustes'
    assert app.radio(key='settings_section').value == 'Contas e cartões'
    assert any(item.value == 'Contas e cartões' for item in app.subheader)


def test_summary_only_shows_recent_five_and_details_are_opt_in(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    seed_demo(path, today=date.today())
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    app = login(AppTest.from_file(APP, default_timeout=15))
    assert app.radio(key="navigation").options == ["Resumo", "Movimentos", "Planejamento", "Ajustes"]
    assert len(app.get("plotly_chart")) == 1
    overview = "\n".join(item.proto.body for item in app.get("html"))
    assert overview.count('<div class="tx-row">') == 5
    assert "Trabalho extra de exemplo" in overview
    assert "Assinatura de exemplo" in overview
    assert "Cinema e passeio" in overview
    assert "Salário de exemplo" not in overview
    assert "Aluguel de exemplo" not in overview
    app.toggle(key="summary_details").set_value(True).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 3
    assert any("Histórico anual" in item.value for item in app.subheader)
    app.toggle(key="summary_details").set_value(False).run()
    assert len(app.get("plotly_chart")) == 1


def test_period_arrows_roll_over_year_without_losing_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCAS_DB_PATH", str(tmp_path / "empty.db"))
    app = login(AppTest.from_file(APP, default_timeout=15))
    app.number_input(key="selected_year").set_value(2025).run()
    app.selectbox(key="selected_month").set_value(12).run()
    app.button(key="next_month").click().run()
    assert not app.exception
    assert app.selectbox(key="selected_month").value == 1
    assert app.number_input(key="selected_year").value == 2026
    app.button(key="previous_month").click().run()
    assert app.selectbox(key="selected_month").value == 12
    assert app.number_input(key="selected_year").value == 2025
    navigate(app, "Planejamento", "planning_section", "Metas")
    assert app.selectbox(key="selected_month").value == 12
    assert app.number_input(key="selected_year").value == 2025


def test_cancel_discards_draft_and_reload_opens_clean_transaction(tmp_path, monkeypatch):
    path = tmp_path / "cancel.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    with closing(get_connection(path)) as db:
        initialize(db)
        create_account(db, "Principal", "corrente", 10000)
    app = login(AppTest.from_file(APP, default_timeout=15))
    click(app, "+ Novo lançamento")
    app.text_input(key="new_tx_description").set_value("Não salvar")
    app.text_input(key="new_tx_amount").set_value("12,34")
    click(app, "Cancelar")
    assert "_transaction_dialog" not in app.session_state
    assert "new_tx_description" not in app.session_state
    assert "new_tx_amount" not in app.session_state
    with closing(get_connection(path)) as db:
        assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
    # AppTest 1.50 retém a árvore de eventos do diálogo já fechado.
    # Validamos o formulário após recarregar; o fechamento visual é manual.
    app = login(AppTest.from_file(APP, default_timeout=15))
    click(app, "+ Novo lançamento")
    assert app.text_input(key="new_tx_description").value == ""
    assert app.text_input(key="new_tx_amount").value == "0,00"


def test_transaction_text_is_escaped_and_negative_balance_is_exact(tmp_path, monkeypatch):
    path = tmp_path / "escaped.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    with closing(get_connection(path)) as db:
        initialize(db)
        account = create_account(db, "Minha conta", "corrente")
        category = list_categories(db)[0]["id"]
        create_transaction(db, date.today(), '<script>alert("x")</script>', 999999999,
                           "despesa", category, account, '<img src=x onerror=alert(1)>')
    app = login(AppTest.from_file(APP, default_timeout=15))
    assert {item.label: item.value for item in app.metric}["Saldo do mês"] == "-R$ 9.999.999,99"
    rendered = "\n".join(item.proto.body for item in app.get("html"))
    assert '<script>alert("x")</script>' not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<img src=x onerror=alert(1)>" not in rendered
