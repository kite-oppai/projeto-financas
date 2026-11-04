import plotly.graph_objects as go
import streamlit as st
from services.finance import monthly_summary, category_spending, daily_spending, annual_summary, top_expenses
from services.money import format_money
from ui.common import MONTH_NAMES, money_axis, transaction_table


def render(db, month):
    st.header('Visão do mês')
    st.caption('Acompanhe suas entradas, gastos e o resultado do período selecionado.')
    summary = monthly_summary(db, month)
    for col, label, current, previous in zip(st.columns(3), ['Receitas', 'Despesas', 'Saldo do mês'],
        ['income_cents', 'expense_cents', 'balance_cents'],
        ['previous_income_cents', 'previous_expense_cents', 'previous_balance_cents']):
        col.metric(label, format_money(summary[current]),
            delta=format_money(summary[current] - summary[previous]) + ' vs. mês anterior',
            delta_color='inverse' if current == 'expense_cents' else 'normal')
    st.caption('Saldo do mês = receitas − despesas. Os saldos das contas incluem o saldo inicial e todo o histórico.')
    by_category, daily = category_spending(db, month), daily_spending(db, month)
    left, right = st.columns(2)
    with left:
        st.subheader('Para onde foi o dinheiro')
        if by_category:
            amounts = [r['amount_cents'] for r in by_category]
            fig = go.Figure(go.Bar(x=[r['category_name'] for r in by_category], y=amounts,
                customdata=[format_money(a) for a in amounts], marker_color='#137C66',
                hovertemplate='%{x}<br>%{customdata}<extra></extra>'))
            st.plotly_chart(money_axis(fig, amounts), use_container_width=True)
        else:
            st.info('As despesas do mês aparecerão aqui.')
    with right:
        st.subheader('Gastos por dia')
        if any(r['amount_cents'] for r in daily):
            amounts = [r['amount_cents'] for r in daily]
            fig = go.Figure(go.Scatter(x=[r['date'] for r in daily], y=amounts, mode='lines+markers',
                customdata=[format_money(a) for a in amounts], line=dict(color='#D17B40'),
                hovertemplate='%{x|%d/%m/%Y}<br>%{customdata}<extra></extra>'))
            fig.update_xaxes(tickformat='%d/%m', title='')
            st.plotly_chart(money_axis(fig, amounts), use_container_width=True)
        else:
            st.info('Ainda não há despesas para mostrar a evolução diária.')
    st.subheader('10 maiores despesas')
    transaction_table(top_expenses(db, month))
    st.subheader('Histórico anual')
    annual = annual_summary(db, int(month[:4]))
    fig, all_amounts = go.Figure(), []
    for label, field, color in [('Receitas', 'income_cents', '#137C66'), ('Despesas', 'expense_cents', '#D17B40')]:
        values = [r[field] for r in annual]
        all_amounts.extend(values)
        fig.add_trace(go.Bar(name=label, x=MONTH_NAMES, y=values, marker_color=color,
            customdata=[format_money(v) for v in values], hovertemplate='%{x}<br>%{customdata}<extra>%{fullData.name}</extra>'))
    fig.update_layout(barmode='group')
    st.plotly_chart(money_axis(fig, all_amounts), use_container_width=True)
    with st.expander('Ver totais de cada mês'):
        st.dataframe([{'Mês': MONTH_NAMES[i], 'Receitas': format_money(r['income_cents']),
            'Despesas': format_money(r['expense_cents']), 'Saldo': format_money(r['balance_cents'])}
            for i, r in enumerate(annual)], hide_index=True, width='stretch')
