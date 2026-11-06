"""Navegação horizontal e competência persistente, sem barra lateral."""
from datetime import date
import streamlit as st
from ui.common import MONTH_NAMES
from ui.auth import logout_button

AREAS = ('Resumo', 'Movimentos', 'Planejamento', 'Ajustes')


def _set_period(year, month):
    st.session_state.pop('_transaction_dialog', None)
    st.session_state['_period_year'] = year
    st.session_state['_period_month'] = month
    st.session_state['selected_year'] = year
    st.session_state['selected_month'] = month


def _shift_period(delta):
    year = st.session_state['_period_year']
    month = st.session_state['_period_month']
    absolute = year * 12 + month - 1 + delta
    year, index = divmod(absolute, 12)
    if 1900 <= year <= 9998:
        _set_period(year, index + 1)


def _choose_period():
    _set_period(st.session_state['selected_year'], st.session_state['selected_month'])


def period_selector():
    today = date.today()
    year = st.session_state.setdefault('_period_year', today.year)
    month = st.session_state.setdefault('_period_month', today.month)
    st.session_state.setdefault('selected_year', year)
    st.session_state.setdefault('selected_month', month)
    with st.container(key='period_controls'):
        previous, current, following = st.columns([1, 3.4, 1], vertical_alignment='center')
        previous.button('‹', key='previous_month', help='Mês anterior', width='stretch',
                        on_click=_shift_period, args=(-1,), disabled=(year, month) == (1900, 1))
        with current.popover(f'{MONTH_NAMES[month - 1]} {year}', width='stretch'):
            st.caption('Escolher competência')
            st.selectbox('Mês', list(range(1, 13)), format_func=lambda n: MONTH_NAMES[n - 1],
                         key='selected_month', on_change=_choose_period)
            st.number_input('Ano', min_value=1900, max_value=9998, step=1,
                            key='selected_year', on_change=_choose_period)
        following.button('›', key='next_month', help='Próximo mês', width='stretch',
                         on_click=_shift_period, args=(1,), disabled=(year, month) == (9998, 12))
    return f'{year:04d}-{month:02d}'


def render():
    with st.container(key='masthead'):
        brand, account = st.columns([5, 1], vertical_alignment='center')
        with brand:
            st.html('<p class="eyebrow">Clareza para o seu dia a dia</p>'
                    '<p class="brand-title">Minhas finanças<span style="color:#737aca">.</span></p>')
        with account:
            logout_button()
    with st.container(key='glass_nav'):
        area = st.radio('Navegação', AREAS, key='navigation', horizontal=True, label_visibility='collapsed',
                        width='stretch', on_change=lambda: st.session_state.pop('_transaction_dialog', None))
    month = period_selector()
    return area, month
