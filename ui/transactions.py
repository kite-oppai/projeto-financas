"""Movimentos compactos; cadastros e edições aparecem somente em diálogos."""
from contextlib import closing
from datetime import date
import os
import sqlite3

import streamlit as st

from database.core import DEFAULT_DB, get_connection
from services.auth import authenticated, load_password_hash
from services.backup import backup_once
from services.finance import (
    create_transaction, delete_transaction, get_transaction, list_accounts,
    list_categories, list_transactions, update_transaction,
)
from services.money import format_date, format_money
from ui.auth import clear_session, require_login
from ui.common import (
    TYPES, amount_input, delete_control, money_value, mutate, page_heading,
    require_catalogs, select_record, transaction_list, transaction_table,
)


def fields(categories, accounts, key, row=None, default_date=None):
    row = row or {}
    when = st.date_input(
        'Data', value=date.fromisoformat(row['date']) if row else (default_date or date.today()),
        format='DD/MM/YYYY', key=f'{key}_date',
    )
    description = st.text_input(
        'Descrição', value=row.get('description', ''), max_chars=200, key=f'{key}_description',
        placeholder='Ex.: mercado, salário ou café',
    )
    value_col, type_col = st.columns(2)
    with value_col:
        amount = amount_input('Valor (R$)', row.get('amount_cents', 0), key=f'{key}_amount')
    with type_col:
        types = list(TYPES)
        kind = st.selectbox('Tipo', types, index=types.index(row.get('type', 'despesa')),
                            format_func=TYPES.get, key=f'{key}_type')
    category = select_record('Categoria', categories, f'{key}_category', selected=row.get('category_id'))
    account = select_record('Conta/cartão', accounts, f'{key}_account', selected=row.get('account_id'))
    with st.expander('Observação (opcional)', expanded=bool(row.get('notes'))):
        notes = st.text_area('Observação', value=row.get('notes', ''), max_chars=5000,
                             key=f'{key}_notes')
    return when, description, amount, kind, category, account, notes


def save(function, db, values, record_id=None):
    try:
        values = list(values)
        values[2] = money_value(values[2])
    except ValueError as exc:
        st.error(str(exc))
        return
    args = [db] + ([record_id] if record_id is not None else []) + values
    mutate(_perform_and_close, function, *args, success='Lançamento salvo.')


def _clear_draft(prefix):
    for key in list(st.session_state):
        if key.startswith(prefix + '_'):
            del st.session_state[key]


def _perform_and_close(function, *args):
    function(*args)
    st.session_state.pop('_transaction_dialog', None)


def _dismiss_dialog():
    dialog = st.session_state.pop('_transaction_dialog', None)
    if dialog:
        prefix = 'new_tx' if dialog['kind'] == 'new' else f"edit_tx_{dialog['id']}"
        _clear_draft(prefix)


def _default_date(month):
    today = date.today()
    return today if month == today.strftime('%Y-%m') else date.fromisoformat(month + '-01')


def _guard_dialog():
    """Fragmentos devem voltar ao login de tela inteira quando a sessão expira."""
    try:
        password_hash = load_password_hash()
    except ValueError:
        clear_session()
        st.rerun(scope='app')
    if not authenticated(st.session_state, password_hash):
        clear_session()
        st.rerun(scope='app')
    require_login()
    backup_once(os.environ.get('FINANCAS_DB_PATH', DEFAULT_DB))


def _cancel(prefix, key):
    if st.button('Cancelar', key=key, width='stretch'):
        _clear_draft(prefix)
        st.session_state.pop('_transaction_dialog', None)
        st.rerun(scope='app')


@st.dialog('Novo lançamento', width='large', on_dismiss=_dismiss_dialog)
def _new_dialog(month):
    try:
        _guard_dialog()
        # Diálogos fazem reruns parciais: não reutilizar a conexão já fechada do app.
        with closing(get_connection()) as db:
            catalogs = require_catalogs(db)
            if not catalogs:
                return
            categories, accounts = catalogs
            st.caption('Registre uma entrada ou saída. Informe sempre um valor positivo.')
            with st.form('transaction_new'):
                values = fields(categories, accounts, 'new_tx', default_date=_default_date(month))
                if st.form_submit_button('Cadastrar lançamento', type='primary', width='stretch'):
                    save(create_transaction, db, values)
            _cancel('new_tx', 'cancel_new_tx')
    except ValueError as exc:
        st.error(str(exc))
    except (sqlite3.Error, OSError):
        st.error('Não foi possível abrir ou salvar o lançamento. Verifique o banco e as permissões da pasta.')


@st.dialog('Editar lançamento', width='large', on_dismiss=_dismiss_dialog)
def _edit_dialog(record_id):
    try:
        _guard_dialog()
        with closing(get_connection()) as db:
            catalogs = require_catalogs(db)
            if not catalogs:
                return
            categories, accounts = catalogs
            row = get_transaction(db, record_id)
            prefix = f'edit_tx_{record_id}'
            st.caption('Alterar a data pode mover o lançamento para outro mês.')
            if row.get('recurrence_id'):
                st.info('Esta edição afeta apenas a ocorrência selecionada, sem alterar a regra recorrente.')
            with st.form(f'transaction_edit_{record_id}'):
                values = fields(categories, accounts, prefix, row)
                if st.form_submit_button('Salvar lançamento', type='primary', width='stretch'):
                    save(update_transaction, db, values, record_id)
            with st.expander('Excluir este lançamento'):
                st.caption('A exclusão é definitiva. Um lançamento recorrente excluído não será gerado novamente.')
                delete_control('Excluir lançamento', f'del_tx_{record_id}', _perform_and_close, delete_transaction, db, record_id)
            _cancel(prefix, f'cancel_edit_tx_{record_id}')
    except ValueError as exc:
        st.error(str(exc))
    except (sqlite3.Error, OSError):
        st.error('Não foi possível abrir ou salvar o lançamento. Verifique o banco e as permissões da pasta.')


def new_transaction_button(db, month, key='new_transaction'):
    """Ação compartilhada pelo Resumo e Movimentos, sem manter conexão no diálogo."""
    ready = bool(list_accounts(db) and list_categories(db))
    if st.button('+ Novo lançamento', key=key, type='primary', disabled=not ready,
                 icon=':material/add:',
                 help=None if ready else 'Cadastre uma conta e uma categoria em Ajustes para começar.'):
        _clear_draft('new_tx')
        st.session_state['_transaction_month'] = month
        st.session_state['_transaction_dialog'] = {'kind': 'new', 'month': month}
    dialog = st.session_state.get('_transaction_dialog')
    if dialog and dialog['kind'] == 'new':
        _new_dialog(dialog['month'])


def filter_transactions(rows, query='', type=None, category_id=None, account_id=None):
    """Filtragem de apresentação, sem recalcular nem alterar valores financeiros."""
    text = query.strip().casefold()
    return [row for row in rows if (
        (not text or text in ' '.join(str(row.get(key, '')) for key in
            ('description', 'category_name', 'account_name', 'notes')).casefold())
        and (type is None or row['type'] == type)
        and (category_id is None or row['category_id'] == category_id)
        and (account_id is None or row['account_id'] == account_id)
    )]


def render(db, month):
    page_heading('Movimentos', 'Entradas e saídas do mês, em um só lugar.')
    catalogs = require_catalogs(db)
    if not catalogs:
        return
    categories, accounts = catalogs
    new_transaction_button(db, month)
    query = st.text_input('Buscar lançamentos', key='transaction_search',
                          placeholder='Descrição, categoria, conta ou observação')
    with st.expander('Filtros avançados'):
        kind = st.selectbox('Tipo de movimento', [None, 'receita', 'despesa'], key='transaction_type_filter',
                            format_func=lambda value: 'Todos os tipos' if value is None else TYPES[value])
        category = st.selectbox('Filtrar por categoria', [None] + [row['id'] for row in categories],
                                key='transaction_category_filter', format_func=lambda value:
                                'Todas as categorias' if value is None else next(row['name'] for row in categories if row['id'] == value))
        account = st.selectbox('Filtrar por conta/cartão', [None] + [row['id'] for row in accounts],
                               key='transaction_account_filter', format_func=lambda value:
                               'Todas as contas' if value is None else next(row['name'] for row in accounts if row['id'] == value))
    rows = list_transactions(db, month)
    filtered = filter_transactions(rows, query, kind, category, account)
    signature = (month, query, kind, category, account)
    if st.session_state.get('_transaction_filter_signature') != signature:
        st.session_state['_transaction_filter_signature'] = signature
        st.session_state['_transaction_visible'] = 20
    visible = st.session_state.get('_transaction_visible', 20)
    st.caption(f'{len(filtered)} lançamento(s)' + (' encontrados' if query or kind or category or account else ' neste mês'))
    transaction_list(filtered[:visible], empty_message='Nenhum lançamento encontrado para este período e filtros.')
    if len(filtered) > visible and st.button('Mostrar mais lançamentos', key='transaction_show_more'):
        st.session_state['_transaction_visible'] = visible + 20
        st.rerun(scope='app')
    if not filtered:
        return
    with st.expander('Gerenciar lançamentos'):
        labels = {row['id']: f"{format_date(row['date'])} · {row['description']} · {format_money(row['amount_cents'])}" for row in filtered}
        selected = st.selectbox('Lançamento', list(labels), format_func=labels.get, key='edit_transaction_id')
        if st.button('Editar lançamento', key='edit_transaction'):
            _clear_draft(f'edit_tx_{selected}')
            st.session_state.pop(f'del_tx_{selected}_confirm', None)
            st.session_state['_transaction_dialog'] = {'kind': 'edit', 'id': selected}
        dialog = st.session_state.get('_transaction_dialog')
        if dialog and dialog['kind'] == 'edit':
            _edit_dialog(dialog['id'])
        if st.checkbox('Mostrar tabela completa', key='transaction_full_table'):
            transaction_table(filtered)
