"""Aplicativo financeiro local: autenticação, inicialização e quatro áreas."""
import os
import sqlite3

import streamlit as st

from database.core import DEFAULT_DB, get_connection, initialize
from services.backup import backup_once
from services.recurring import generate_due
from ui import budgets, catalogs, dashboard, goals, imports, recurrences, shell, transactions
from ui.auth import require_login
from ui.common import flash, page_heading
from ui.styles import apply_styles

st.set_page_config(page_title='Minhas finanças', page_icon='💠', layout='wide')


def settings_info():
    page_heading('Seu espaço privado', 'Dados no seu PC, acesso pela sua rede.')
    st.markdown('**Login e senha**  \nA sessão expira após 30 minutos sem interação. Para trocar a senha, '
                'execute no PC `scripts/configurar_senha.py`.')
    st.markdown('**Cópias de segurança**  \nO aplicativo mantém sete backups por banco, na pasta '
                '`backups` ao lado dele. Encerre o app antes de restaurar uma cópia.')
    st.markdown('**Acesso pelo celular**  \nUse a rede Tailscale com o PC ligado e sem suspensão. '
                'Não utilize Funnel nem encaminhamento de portas. O passo a passo está no README.')
    st.caption('O saldo mensal considera os movimentos daquele mês. Contas e cartões mostram todo o histórico.')


def main():
    apply_styles()
    require_login()
    area, month = shell.render()
    db = None
    try:
        backup_once(os.environ.get('FINANCAS_DB_PATH', DEFAULT_DB))
        db = get_connection()
        initialize(db)
        generated = generate_due(db)
        flash()
        if generated:
            st.info(f'{generated} lançamento(s) recorrente(s) gerado(s) até hoje.')
        if area == 'Resumo':
            dashboard.render(db, month)
        elif area == 'Movimentos':
            section = st.radio('Movimentos', ['Lançamentos', 'Importar e exportar'],
                               key='movements_section', horizontal=True, label_visibility='collapsed')
            (transactions.render if section == 'Lançamentos' else imports.render)(db, month)
        elif area == 'Planejamento':
            section = st.radio('Planejamento', ['Orçamento', 'Recorrências', 'Metas'],
                               key='planning_section', horizontal=True, label_visibility='collapsed')
            {'Orçamento': budgets.render, 'Recorrências': recurrences.render, 'Metas': goals.render}[section](db, month)
        else:
            section = st.radio('Ajustes', ['Contas e cartões', 'Categorias', 'Sobre e segurança'],
                               key='settings_section', horizontal=True, label_visibility='collapsed')
            if section == 'Contas e cartões':
                catalogs.accounts_page(db)
            elif section == 'Categorias':
                catalogs.categories_page(db)
            else:
                settings_info()
    except ValueError as exc:
        st.error(str(exc))
    except sqlite3.Error:
        st.error('Não foi possível acessar o banco de dados. Verifique a pasta data e as permissões de leitura e escrita. Feche outras operações que estejam bloqueando o arquivo e tente novamente.')
    except OSError:
        st.error('Não foi possível ler ou gravar um arquivo local. Verifique o caminho, as permissões e o espaço disponível em disco.')
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    main()
