import streamlit as st
from services.finance import (list_categories, create_category, update_category, delete_category,
    list_accounts, create_account, update_account, delete_account)
from services.money import format_money
from ui.common import KINDS, amount_input, money_value, mutate, select_record, delete_control, page_heading


def _close(key):
    st.session_state[key] = None


def _close_button(key):
    st.button('Fechar formulário', key=f'{key}_close', on_click=_close, args=(key,))


def categories_page(db):
    page_heading('Categorias', 'Organize seus movimentos sem perder o histórico.')
    rows = list_categories(db)
    if rows:
        st.caption(f'{len(rows)} categorias disponíveis')
        # Componente nativo: nomes são conteúdo, nunca HTML executável.
        st.dataframe([{'Categoria': r['name']} for r in rows], hide_index=True, width='stretch')
    else:
        st.info('Adicione uma categoria para organizar seus lançamentos.')
    options = ['Adicionar categoria'] + (['Editar ou excluir'] if rows else [])
    action = st.selectbox('Gerenciar categorias', options, index=None,
        placeholder='Escolha uma ação', key='categories_action')
    if action == 'Adicionar categoria':
        with st.form('category_new'):
            name = st.text_input('Nome da nova categoria', max_chars=100)
            if st.form_submit_button('Criar categoria', type='primary'):
                mutate(create_category, db, name, success='Categoria criada.')
    elif action == 'Editar ou excluir':
        selected = select_record('Categoria', rows, 'category_edit_id')
        row = next(r for r in rows if r['id'] == selected)
        with st.form(f'category_edit_{selected}'):
            name = st.text_input('Nome', value=row['name'], max_chars=100)
            if st.form_submit_button('Salvar categoria'):
                mutate(update_category, db, selected, name, success='Categoria salva.')
        st.caption('Categorias em uso podem ser renomeadas. Para excluir, remova antes os vínculos com lançamentos, limites e recorrências.')
        delete_control('Excluir categoria', f'del_category_{selected}', delete_category, db, selected)
    if action:
        _close_button('categories_action')


def account_fields(key, row=None):
    row = row or {}
    name = st.text_input('Nome da conta/cartão', value=row.get('name', ''), max_chars=100, key=f'{key}_name')
    kinds = list(KINDS)
    kind = st.selectbox('Modalidade', kinds, index=kinds.index(row.get('kind', 'corrente')), format_func=KINDS.get, key=f'{key}_kind')
    opening = amount_input('Saldo inicial (R$)', row.get('initial_balance_cents', 0), key=f'{key}_balance',
        help='Aceita saldo negativo. Para cartão, informe a dívida inicial com sinal negativo.')
    return name, kind, opening


def save_account(function, db, values, selected=None):
    try:
        name, kind, opening = values
        opening = money_value(opening)
    except ValueError as exc:
        st.error(str(exc))
        return
    args = [db] + ([selected] if selected is not None else []) + [name, kind, opening]
    mutate(function, *args, success='Conta/cartão salvo.')


def accounts_page(db):
    page_heading('Contas e cartões', 'Saldos de todo o histórico, incluindo o saldo inicial.')
    rows = list_accounts(db)
    if rows:
        st.dataframe([{'Nome': r['name'], 'Modalidade': KINDS[r['kind']],
            'Saldo inicial': format_money(r['initial_balance_cents']), 'Saldo atual': format_money(r['balance_cents'])}
            for r in rows], hide_index=True, width='stretch')
    else:
        st.info('Comece cadastrando sua primeira conta.')
    with st.expander('Como os saldos são calculados'):
        st.write('Saldo inicial + receitas − despesas de todo o histórico, inclusive lançamentos futuros. Em cartões, saldo negativo representa dívida. Compras entram integralmente na data informada; faturas e parcelamento não fazem parte deste MVP.')
    options = ['Adicionar conta/cartão'] + (['Editar ou excluir'] if rows else [])
    action = st.selectbox('Gerenciar contas e cartões', options, index=None,
        placeholder='Escolha uma ação', key='accounts_action')
    if action == 'Adicionar conta/cartão':
        with st.form('account_new'):
            values = account_fields('new_account')
            if st.form_submit_button('Criar conta/cartão', type='primary'):
                save_account(create_account, db, values)
    elif action == 'Editar ou excluir':
        selected = select_record('Conta/cartão', rows, 'account_edit_id')
        row = next(r for r in rows if r['id'] == selected)
        with st.form(f'account_edit_{selected}'):
            values = account_fields(f'edit_account_{selected}', row)
            if st.form_submit_button('Salvar conta/cartão'):
                save_account(update_account, db, values, selected)
        delete_control('Excluir conta/cartão', f'del_account_{selected}', delete_account, db, selected)
    if action:
        _close_button('accounts_action')
