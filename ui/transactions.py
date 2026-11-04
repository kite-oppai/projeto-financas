from datetime import date
import streamlit as st
from services.finance import list_transactions, create_transaction, update_transaction, delete_transaction
from services.money import format_date, format_money
from ui.common import amount_input, money_value, mutate, require_catalogs, select_record, transaction_table, delete_control, TYPES


def fields(categories, accounts, key, row=None, default_date=None):
    row = row or {}
    when = st.date_input('Data', value=date.fromisoformat(row['date']) if row else (default_date or date.today()), format='DD/MM/YYYY', key=f'{key}_date')
    description = st.text_input('Descrição', value=row.get('description', ''), max_chars=200, key=f'{key}_description')
    amount = amount_input('Valor (R$)', row.get('amount_cents', 0), key=f'{key}_amount')
    types = list(TYPES)
    kind = st.selectbox('Tipo', types, index=types.index(row.get('type', 'despesa')), format_func=TYPES.get, key=f'{key}_type')
    category = select_record('Categoria', categories, f'{key}_category', selected=row.get('category_id'))
    account = select_record('Conta/cartão', accounts, f'{key}_account', selected=row.get('account_id'))
    notes = st.text_area('Observação', value=row.get('notes', ''), key=f'{key}_notes')
    return when, description, amount, kind, category, account, notes


def save(function, db, values, record_id=None):
    try:
        values = list(values)
        values[2] = money_value(values[2])
    except ValueError as exc:
        st.error(str(exc))
        return
    args = [db] + ([record_id] if record_id is not None else []) + values
    mutate(function, *args, success='Lançamento salvo.')


def render(db, month):
    st.header('Lançamentos')
    catalogs = require_catalogs(db)
    if not catalogs:
        return
    categories, accounts = catalogs
    rows = list_transactions(db, month)
    st.subheader('Movimentações do mês')
    transaction_table(rows)
    today = date.today()
    default_date = today if month == today.strftime('%Y-%m') else date.fromisoformat(month + '-01')
    if st.session_state.get('_transaction_month') != month:
        if 'new_tx_date' in st.session_state:
            st.session_state['new_tx_date'] = default_date
        st.session_state['_transaction_month'] = month
    with st.expander('Novo lançamento', expanded=True):
        with st.form('transaction_new'):
            values = fields(categories, accounts, 'new_tx', default_date=default_date)
            if st.form_submit_button('Cadastrar lançamento', type='primary'):
                save(create_transaction, db, values)
    if rows:
        st.subheader('Editar ou excluir')
        st.caption('Se você alterar a data para outro mês, o lançamento passará a aparecer no período correspondente.')
        labels = {r['id']: f"{format_date(r['date'])} · {r['description']} · {format_money(r['amount_cents'])}" for r in rows}
        selected = st.selectbox('Lançamento', list(labels), format_func=labels.get, key='edit_transaction_id')
        row = next(r for r in rows if r['id'] == selected)
        if row.get('recurrence_id'):
            st.caption('Este lançamento foi gerado por uma recorrência. A alteração afeta apenas esta ocorrência.')
        with st.form(f'transaction_edit_{selected}'):
            values = fields(categories, accounts, f'edit_tx_{selected}', row)
            if st.form_submit_button('Salvar lançamento'):
                save(update_transaction, db, values, selected)
        delete_control('Excluir lançamento', f'del_tx_{selected}', delete_transaction, db, selected)
