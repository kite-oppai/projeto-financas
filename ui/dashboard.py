"""Resumo enxuto; as análises completas aparecem somente quando solicitadas."""
from html import escape

import plotly.graph_objects as go
import streamlit as st

from services.finance import (annual_summary, category_spending, daily_spending,
                              list_accounts, list_categories, list_transactions, monthly_summary, top_expenses)
from services.money import format_date, format_money
from ui.common import MONTH_NAMES, money_axis, page_heading, transaction_list, transaction_table
from ui.transactions import new_transaction_button


CHART_CONFIG = {'displayModeBar': False, 'responsive': True}


def _open_settings(section):
    st.session_state['navigation'] = 'Ajustes'
    st.session_state['settings_section'] = section


def category_chart(db, month):
    rows = category_spending(db, month)
    if not rows:
        st.info('Suas despesas por categoria aparecerão aqui. Comece com um novo lançamento.')
        return
    amounts = [r['amount_cents'] for r in rows]
    # Centavos inteiros nos dados; nomes e rótulos de hover nunca viram HTML livre.
    labels = [r['category_name'] for r in rows]
    fig = go.Figure(go.Bar(
        x=[escape(name if len(name) <= 18 else name[:17] + '…') for name in labels], y=amounts,
        customdata=[[escape(name), format_money(value)] for name, value in zip(labels, amounts)],
        marker=dict(color='#818bc9', cornerradius=7),
        hovertemplate='%{customdata[0]}<br>%{customdata[1]}<extra></extra>',
    ))
    fig.update_layout(height=285, bargap=.52)
    st.plotly_chart(money_axis(fig, amounts), use_container_width=True, config=CHART_CONFIG, key='category_chart')


def details(db, month, summary):
    page_heading('Em perspectiva', 'Comparação com o mês anterior, evolução e histórico anual.')
    comparison = []
    for label, field in [('Receitas', 'income_cents'), ('Despesas', 'expense_cents'), ('Saldo do mês', 'balance_cents')]:
        previous = summary['previous_' + field]
        comparison.append({'Indicador': label, 'Mês atual': format_money(summary[field]),
                           'Mês anterior': format_money(previous),
                           'Variação': format_money(summary[field] - previous)})
    st.dataframe(comparison, hide_index=True, width='stretch')
    page_heading('Gastos por dia')
    daily = daily_spending(db, month)
    amounts = [r['amount_cents'] for r in daily]
    if any(amounts):
        fig = go.Figure(go.Scatter(
            x=[r['date'] for r in daily], y=amounts, mode='lines+markers',
            customdata=[[format_date(r['date']), format_money(r['amount_cents'])] for r in daily],
            line=dict(color='#818bc9', width=2), marker=dict(size=5),
            hovertemplate='%{customdata[0]}<br>%{customdata[1]}<extra></extra>',
        ))
        fig.update_xaxes(tickformat='%d/%m', title='')
        fig.update_layout(height=260)
        st.plotly_chart(money_axis(fig, amounts), use_container_width=True, config=CHART_CONFIG, key='daily_chart')
    else:
        st.info('Ainda não há despesas para mostrar a evolução diária.')
    page_heading('10 maiores despesas')
    transaction_table(top_expenses(db, month))
    page_heading('Histórico anual')
    annual = annual_summary(db, int(month[:4]))
    fig, values = go.Figure(), []
    for label, field, color in [('Receitas', 'income_cents', '#468d7b'), ('Despesas', 'expense_cents', '#bc8393')]:
        amounts = [r[field] for r in annual]
        values.extend(amounts)
        fig.add_trace(go.Bar(name=label, x=MONTH_NAMES, y=amounts, marker=dict(color=color, cornerradius=4),
                            customdata=[format_money(v) for v in amounts],
                            hovertemplate='%{x}<br>%{customdata}<extra>%{fullData.name}</extra>'))
    fig.update_layout(barmode='group', height=285, legend=dict(orientation='h', y=1.15, x=0))
    st.plotly_chart(money_axis(fig, values), use_container_width=True, config=CHART_CONFIG, key='annual_chart')
    with st.expander('Totais mês a mês'):
        st.dataframe([{'Mês': MONTH_NAMES[i], 'Receitas': format_money(r['income_cents']),
                       'Despesas': format_money(r['expense_cents']), 'Saldo': format_money(r['balance_cents'])}
                      for i, r in enumerate(annual)], hide_index=True, width='stretch')


def render(db, month):
    title, action = st.columns([2, 1], vertical_alignment='center')
    with title:
        page_heading('Seu mês, com clareza')
    with action:
        new_transaction_button(db, month, key='summary_new_transaction')
    if not list_accounts(db):
        st.info('Comece cadastrando uma conta ou cartão. Depois você poderá registrar seus ganhos e gastos.')
        st.button('Cadastrar primeira conta', on_click=_open_settings, args=('Contas e cartões',))
    elif not list_categories(db):
        st.info('Cadastre uma categoria para organizar seus próximos lançamentos.')
        st.button('Cadastrar categoria', on_click=_open_settings, args=('Categorias',))
    summary = monthly_summary(db, month)
    with st.container(key='glass_hero'):
        st.html('<p class="eyebrow">O essencial, em um olhar</p>')
        st.metric('Saldo do mês', format_money(summary['balance_cents']))
        st.caption('Receitas − despesas deste mês. Os saldos das contas ficam em Ajustes.')
        with st.container(key='cashflow'):
            income, expense = st.columns(2)
            income.metric('Receitas', format_money(summary['income_cents']))
            expense.metric('Despesas', format_money(summary['expense_cents']))
    graph, recent = st.columns([1.15, 1], gap='large')
    with graph:
        page_heading('Para onde foi o dinheiro')
        category_chart(db, month)
    with recent:
        page_heading('Últimos movimentos', 'Os cinco lançamentos mais recentes deste mês.')
        transaction_list(list_transactions(db, month)[:5])
        st.caption('Todos os lançamentos e filtros estão em Movimentos.')
    if st.toggle('Ver detalhes', value=False, key='summary_details'):
        details(db, month, summary)
