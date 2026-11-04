from tests.ui_helpers import login
"""Fluxos reais do Streamlit com bases temporárias, sem iniciar servidor."""
from datetime import date
from contextlib import closing
from pathlib import Path

from streamlit.testing.v1 import AppTest

from database.core import get_connection
from services.finance import list_accounts
from seed import seed_demo


APP = str(Path(__file__).resolve().parents[1] / "app.py")
PAGES = [
    "Visão geral", "Lançamentos", "Contas e cartões", "Categorias",
    "Orçamento", "Importar e exportar", "Recorrências", "Metas",
]


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def navigate(app, page):
    app.radio(key="navigation").set_value(page).run()
    assert not app.exception


def test_empty_database_all_pages_render(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCAS_DB_PATH", str(tmp_path / "empty.db"))
    app = login(AppTest.from_file(APP, default_timeout=15))
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["R$ 0,00"] * 3
    for page in PAGES:
        navigate(app, page)


def test_demo_dashboard_and_budget_alerts(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    seed_demo(path, today=date.today())
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    app = login(AppTest.from_file(APP, default_timeout=15))
    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics == {
        "Receitas": "R$ 6.950,00", "Despesas": "R$ 2.810,70", "Saldo do mês": "R$ 4.139,30"
    }
    assert len(app.get("plotly_chart")) == 3
    navigate(app, "Orçamento")
    assert any("80%" in warning.value for warning in app.warning)
    assert any("100%" in error.value for error in app.error)
    assert any("dentro do limite" in success.value for success in app.success)
    for page in PAGES:
        navigate(app, page)


def test_account_transaction_validation_and_confirmed_deletion(tmp_path, monkeypatch):
    path = tmp_path / "personal.db"
    monkeypatch.setenv("FINANCAS_DB_PATH", str(path))
    app = login(AppTest.from_file(APP, default_timeout=15))
    navigate(app, "Contas e cartões")
    app.text_input(key="new_account_name").set_value("Carteira")
    app.text_input(key="new_account_balance").set_value("100,00")
    click(app, "Criar conta/cartão")
    navigate(app, "Lançamentos")
    app.text_input(key="new_tx_description").set_value("Café")
    app.text_input(key="new_tx_amount").set_value("0.001")
    click(app, "Cadastrar lançamento")
    assert app.error
    with closing(get_connection(path)) as db:
        assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
    app.text_input(key="new_tx_amount").set_value("10,01")
    click(app, "Cadastrar lançamento")
    with closing(get_connection(path)) as db:
        transaction = db.execute("SELECT id, amount_cents FROM transactions").fetchone()
        assert transaction["amount_cents"] == 1001
        assert list_accounts(db)[0]["balance_cents"] == 8999
    delete = next(button for button in app.button if button.label == "Excluir lançamento")
    assert delete.disabled
    app.checkbox(key=f"del_tx_{transaction['id']}_confirm").check().run()
    click(app, "Excluir lançamento")
    with closing(get_connection(path)) as db:
        assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
        assert list_accounts(db)[0]["balance_cents"] == 10000
