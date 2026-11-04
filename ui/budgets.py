import streamlit as st
from services.finance import list_categories, budget_status, set_budget, delete_budget
from services.money import format_money
from ui.common import amount_input, money_value, mutate, select_record, delete_control


def render(db, month):
    st.header('Orçamento mensal')
    st.caption('Os limites valem para o mês selecionado. Receitas não reduzem o gasto de uma categoria.')
    rows = budget_status(db, month)
    if not rows:
        st.info('Defina seu primeiro limite por categoria para acompanhar o orçamento.')
    for row in rows:
        with st.container(border=True):
            st.subheader(row['category_name'])
            cols = st.columns(3)
            cols[0].metric('Limite', format_money(row['limit_cents']))
            cols[1].metric('Gasto', format_money(row['spent_cents']))
            cols[2].metric('Restante', format_money(row['remaining_cents']))
            percent = row['spent_cents'] * 100 // row['limit_cents']
            st.progress(min(100, percent), text=f'{percent}% do limite utilizado')
            if row['status'] == 'excedido':
                st.error('Limite atingido ou ultrapassado (100% ou mais).')
            elif row['status'] == 'atencao':
                st.warning('Atenção: você já utilizou pelo menos 80% do orçamento.')
            else:
                st.success('Gastos dentro do limite.')
    categories = list_categories(db)
    if not categories:
        st.info('Cadastre uma categoria para definir um orçamento.')
        return
    with st.form('budget_save'):
        st.subheader('Definir ou atualizar limite')
        category = select_record('Categoria', categories, 'budget_category')
        amount = amount_input('Limite mensal (R$)', key='budget_limit')
        if st.form_submit_button('Salvar limite', type='primary'):
            try:
                cents = money_value(amount)
            except ValueError as exc:
                st.error(str(exc))
            else:
                mutate(set_budget, db, month, category, cents, success='Orçamento salvo.')
    if rows:
        with st.expander('Remover um limite'):
            selected = select_record('Categoria com limite', rows, 'budget_delete_id', name='category_name')
            delete_control('Excluir limite', f'del_budget_{selected}', delete_budget, db, selected)
