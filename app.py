"""Aplicativo local de controle financeiro pessoal. Execute na raiz do projeto."""
from datetime import date
import sqlite3
import streamlit as st
from database.core import get_connection, initialize
from services.recurring import generate_due
from ui import dashboard, transactions, catalogs, budgets, imports, recurrences, goals
from ui.common import MONTH_NAMES, flash

st.set_page_config(page_title='Minhas finanças', page_icon='💰', layout='wide')


def main():
    with st.sidebar:
        st.title('Minhas finanças')
        st.caption('Seu dinheiro, sob seu controle.')
        page = st.radio('Navegação', ['Visão geral', 'Lançamentos', 'Contas e cartões', 'Categorias',
            'Orçamento', 'Importar e exportar', 'Recorrências', 'Metas'], key='navigation')
        st.divider()
        st.subheader('Período')
        today = date.today()
        month = st.selectbox('Mês', list(range(1, 13)), index=today.month - 1,
            format_func=lambda n: MONTH_NAMES[n - 1], key='selected_month')
        year = st.number_input('Ano', min_value=1900, max_value=9998, value=today.year, step=1, key='selected_year')
        st.caption('O período filtra a visão geral, os lançamentos e o orçamento. Contas, metas e recorrências mostram todo o histórico.')
        st.divider()
        st.caption('🔒 Dados locais em SQLite. Sem integrações ou envio de dados financeiros à internet.')
    db = None
    try:
        db = get_connection()
        initialize(db)
        generated = generate_due(db)
        flash()
        if generated:
            st.info(f'{generated} lançamento(s) recorrente(s) gerado(s) até hoje.')
        month_key = f'{year:04d}-{month:02d}'
        st.caption(f'{MONTH_NAMES[month - 1]} de {year}')
        handlers = {
            'Visão geral': dashboard.render,
            'Lançamentos': transactions.render,
            'Contas e cartões': lambda db, month: catalogs.accounts_page(db),
            'Categorias': lambda db, month: catalogs.categories_page(db),
            'Orçamento': budgets.render,
            'Importar e exportar': imports.render,
            'Recorrências': recurrences.render,
            'Metas': goals.render,
        }
        handlers[page](db, month_key)
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
