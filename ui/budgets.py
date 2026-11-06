import streamlit as st
from services.finance import list_categories, budget_status, set_budget, delete_budget
from services.money import format_money
from ui.common import amount_input, money_value, mutate, select_record, delete_control, page_heading, status_pill


def _close():
    st.session_state['budget_action'] = None


def render(db, month):
    page_heading('Orçamento mensal', 'Quanto você gastou e quanto ainda pode usar no mês selecionado.')
    rows = budget_status(db, month)
    if not rows:
        st.info('Defina seu primeiro limite por categoria para acompanhar o orçamento.')
    for row in rows:
        with st.container():
            st.write(row['category_name'])
            st.write(f"Gasto {format_money(row['spent_cents'])} · Limite {format_money(row['limit_cents'])}")
            percent = row['spent_cents'] * 100 // row['limit_cents']
            st.caption(f"Restante: {format_money(row['remaining_cents'])} · {percent}% utilizado")
            if row['status'] == 'excedido':
                st.error('Limite atingido ou ultrapassado (100% ou mais).')
            elif row['status'] == 'atencao':
                st.warning('Atenção: você já utilizou pelo menos 80% do orçamento.')
            else:
                status_pill('Gastos dentro do limite.', 'success')
    categories = list_categories(db)
    if not categories:
        st.info('Cadastre uma categoria para definir um orçamento.')
        return
    options = ['Definir ou atualizar limite'] + (['Remover limite'] if rows else [])
    action = st.selectbox('Gerenciar limites', options, index=None,
        placeholder='Escolha uma ação', key='budget_action')
    if action == 'Definir ou atualizar limite':
        with st.form('budget_save'):
            category = select_record('Categoria', categories, 'budget_category')
            amount = amount_input('Limite mensal (R$)', key='budget_limit')
            if st.form_submit_button('Salvar limite', type='primary'):
                try:
                    cents = money_value(amount)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    mutate(set_budget, db, month, category, cents, success='Orçamento salvo.')
    elif action == 'Remover limite':
        selected = select_record('Categoria com limite', rows, 'budget_delete_id', name='category_name')
        delete_control('Excluir limite', f'del_budget_{selected}', delete_budget, db, selected)
    if action:
        st.button('Fechar formulário', key='budget_action_close', on_click=_close)
    with st.expander('Entenda o orçamento'):
        st.write('O limite vale apenas para esta categoria e competência. Receitas não reduzem os gastos. Há atenção em 80% e alerta de limite atingido ou ultrapassado em 100%.')
