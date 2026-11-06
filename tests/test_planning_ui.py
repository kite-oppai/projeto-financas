"""Gerenciamento sob demanda conserva cadastros, recorrências e aportes."""
from contextlib import closing
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from database.core import get_connection, initialize
from services.finance import create_account, list_accounts
from tests.ui_helpers import login


APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def start(tmp_path, monkeypatch):
    path = tmp_path / 'planejamento.db'
    monkeypatch.setenv('FINANCAS_DB_PATH', str(path))
    with closing(get_connection(path)) as db:
        initialize(db)
        create_account(db, 'Principal', 'corrente', 50000)
    return login(AppTest.from_file(APP, default_timeout=15)), path


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def navigate(app, area, section):
    app.radio(key='navigation').set_value(area).run()
    section_key = {'Planejamento': 'planning_section', 'Ajustes': 'settings_section'}[area]
    app.radio(key=section_key).set_value(section).run()
    assert not app.exception


def test_account_edit_and_category_reference_protection(tmp_path, monkeypatch):
    app, path = start(tmp_path, monkeypatch)
    navigate(app, 'Ajustes', 'Contas e cartões')
    assert not app.text_input  # Nenhum formulário fica aberto inicialmente.
    app.selectbox(key='accounts_action').set_value('Editar ou excluir').run()
    app.text_input(key='edit_account_1_name').set_value('Principal revisada')
    app.text_input(key='edit_account_1_balance').set_value('501,01')
    click(app, 'Salvar conta/cartão')
    with closing(get_connection(path)) as db:
        account = list_accounts(db)[0]
        assert account['name'] == 'Principal revisada'
        assert account['balance_cents'] == 50101
    navigate(app, 'Ajustes', 'Categorias')
    app.selectbox(key='categories_action').set_value('Adicionar categoria').run()
    next(field for field in app.text_input if field.label == 'Nome da nova categoria').set_value('Pets')
    click(app, 'Criar categoria')
    with closing(get_connection(path)) as db:
        category = db.execute("SELECT id FROM categories WHERE name='Pets'").fetchone()[0]
        db.execute('INSERT INTO budgets(month,category_id,limit_cents) VALUES (?,?,?)',
                   (date.today().strftime('%Y-%m'), category, 1000))
        db.commit()
    app.selectbox(key='categories_action').set_value('Editar ou excluir').run()
    app.selectbox(key='category_edit_id').set_value(category).run()
    assert next(b for b in app.button if b.label == 'Excluir categoria').disabled
    app.checkbox(key=f'del_category_{category}_confirm').check().run()
    click(app, 'Excluir categoria')
    assert any('em uso' in item.value for item in app.error)
    with closing(get_connection(path)) as db:
        assert db.execute('SELECT 1 FROM categories WHERE id=?', (category,)).fetchone()


def test_goal_contributions_change_progress_without_changing_balance(tmp_path, monkeypatch):
    app, path = start(tmp_path, monkeypatch)
    navigate(app, 'Planejamento', 'Metas')
    assert not app.text_input
    app.selectbox(key='goals_action').set_value('Adicionar meta').run()
    app.text_input(key='new_goal_name').set_value('Viagem')
    app.text_input(key='new_goal_amount').set_value('100,00')
    click(app, 'Criar meta')
    with closing(get_connection(path)) as db:
        goal = db.execute('SELECT id FROM goals').fetchone()[0]
    app.selectbox(key='goals_action').set_value('Registrar aporte').run()
    app.text_input(key=f'contribution_amount_{goal}').set_value('25,01')
    click(app, 'Registrar aporte')
    assert not app.get('progress')
    assert any('25% do objetivo' in text.value for text in app.caption)
    with closing(get_connection(path)) as db:
        contribution = db.execute('SELECT id,amount_cents FROM goal_contributions').fetchone()
        assert contribution['amount_cents'] == 2501
        assert list_accounts(db)[0]['balance_cents'] == 50000
    app.selectbox(key='goals_action').set_value('Excluir aporte').run()
    app.checkbox(key=f"del_contribution_{contribution['id']}_confirm").check().run()
    click(app, 'Excluir aporte')
    with closing(get_connection(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM goal_contributions').fetchone()[0] == 0
    app.selectbox(key='goals_action').set_value('Editar ou excluir').run()
    app.checkbox(key=f'del_goal_{goal}_confirm').check().run()
    click(app, 'Excluir meta e aportes')
    with closing(get_connection(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM goals').fetchone()[0] == 0


def test_recurring_rule_editor_preserves_generated_history(tmp_path, monkeypatch):
    app, path = start(tmp_path, monkeypatch)
    navigate(app, 'Planejamento', 'Recorrências')
    app.selectbox(key='recurring_action').set_value('Adicionar recorrência').run()
    app.text_input(key='new_rule_description').set_value('Assinatura')
    app.text_input(key='new_rule_amount').set_value('10,01')
    click(app, 'Criar recorrência')
    with closing(get_connection(path)) as db:
        rule = db.execute('SELECT id FROM recurring_rules').fetchone()[0]
        assert db.execute('SELECT amount_cents FROM transactions').fetchone()[0] == 1001
    app.selectbox(key='recurring_action').set_value('Editar ou excluir').run()
    app.text_input(key=f'edit_rule_{rule}_amount').set_value('20,99')
    app.checkbox(key=f'edit_rule_{rule}_active').uncheck().run()
    click(app, 'Salvar recorrência')
    with closing(get_connection(path)) as db:
        changed = db.execute('SELECT amount_cents,active FROM recurring_rules').fetchone()
        assert tuple(changed) == (2099, 0)
        assert db.execute('SELECT amount_cents FROM transactions').fetchone()[0] == 1001
    app.checkbox(key=f'del_rule_{rule}_confirm').check().run()
    click(app, 'Excluir recorrência')
    with closing(get_connection(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM recurring_rules').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] == 1
