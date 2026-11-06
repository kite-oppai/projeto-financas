"""Composição da interface, com moeda brasileira e mensagens locais."""
import sqlite3
from html import escape
import streamlit as st
from services.money import format_money, format_date, parse_money

MONTH_NAMES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
KINDS = {'corrente': 'Conta corrente', 'poupanca': 'Poupança', 'dinheiro': 'Dinheiro', 'credito': 'Cartão de crédito'}
TYPES = {'despesa': 'Despesa', 'receita': 'Receita'}


def amount_input(label, cents=0, key=None, help=None):
    return st.text_input(label, value=format_money(cents).replace('R$ ', ''), key=key,
                        help=help or 'Use reais e centavos, por exemplo: 1.234,56.')


def money_value(text):
    return parse_money(text)


def mutate(function, *args, success='Alteração salva.', **kwargs):
    try:
        function(*args, **kwargs)
    except ValueError as exc:
        st.error(str(exc))
    except sqlite3.Error:
        st.error('Não foi possível salvar. Verifique os dados e se o banco está disponível para escrita.')
    else:
        st.session_state['_flash'] = success
        st.rerun(scope='app')


def flash():
    message = st.session_state.pop('_flash', None)
    if message:
        for key in list(st.session_state):
            if key.endswith('_confirm') or key.startswith('import_confirm_') or key == 'import_include_duplicates':
                del st.session_state[key]
        st.success(message)


def select_record(label, records, key, name='name', selected=None):
    ids = [r['id'] for r in records]
    labels = {r['id']: r[name] for r in records}
    index = ids.index(selected) if selected in ids else 0
    return st.selectbox(label, ids, index=index, format_func=labels.get, key=key)


def require_catalogs(db):
    from services.finance import list_categories, list_accounts
    categories, accounts = list_categories(db), list_accounts(db)
    if not accounts:
        st.info('Cadastre uma conta ou cartão na página Contas e cartões para começar.')
        return None
    if not categories:
        st.info('Cadastre uma categoria na página Categorias para começar.')
        return None
    return categories, accounts


def transaction_table(rows):
    if not rows:
        st.info('Nenhum lançamento neste período.')
        return
    st.dataframe([{'Data': format_date(r['date']), 'Descrição': r['description'],
        'Valor': format_money(r['amount_cents']), 'Tipo': TYPES[r['type']],
        'Categoria': r['category_name'], 'Conta/cartão': r['account_name'],
        'Observação': r.get('notes', '')} for r in rows], hide_index=True, width='stretch')


def delete_control(label, key, function, *args):
    confirmed = st.checkbox('Confirmo a exclusão.', key=f'{key}_confirm')
    if st.button(label, key=f'{key}_delete', disabled=not confirmed):
        mutate(function, *args, success='Registro excluído.')


def money_axis(fig, amounts, axis='y'):
    high = max([abs(v) for v in amounts] or [0])
    step = max(1, (high + 3) // 4)
    ticks = [step * i for i in range(5)]
    kwargs = dict(tickmode='array', tickvals=ticks, ticktext=[format_money(v) for v in ticks], title='')
    getattr(fig, f'update_{axis}axes')(**kwargs)
    fig.update_layout(margin=dict(l=8, r=8, t=16, b=8), font=dict(family='sans-serif', color='#606b82'),
        legend_title_text='', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        colorway=['#6870ba', '#a9b3e6', '#8f83b5', '#bacbdc', '#c6c2e4'],
        hoverlabel=dict(bgcolor='#ffffff', font_color='#202d49'))
    fig.update_yaxes(gridcolor='rgba(96,107,130,.08)', zeroline=False)
    fig.update_xaxes(showgrid=False, zeroline=False)
    return fig


def page_heading(title, description=None):
    st.subheader(title)
    if description:
        st.caption(description)


def status_pill(text, tone='neutral'):
    tone = tone if tone in ('neutral', 'success', 'warning', 'danger') else 'neutral'
    st.html(f'<span class="status-pill status-pill--{tone}">{escape(str(text))}</span>')


def transaction_list(rows, empty_message='Nenhum lançamento neste período.'):
    """Lista de leitura; dados do usuário são escapados antes de compor HTML."""
    if not rows:
        st.info(empty_message)
        return
    items = []
    for row in rows:
        kind = row['type']
        tone = 'income' if kind == 'receita' else 'expense'
        sign = '+' if kind == 'receita' else '−'
        meta = ' · '.join((format_date(row['date']), row['category_name'], row['account_name']))
        items.append(f'<div class="tx-row"><div><div class="tx-description">'
                     f'{escape(row["description"])}</div><div class="tx-meta">{escape(meta)}</div></div>'
                     f'<div class="tx-amount tx-{tone}" aria-label="{TYPES[kind]} {escape(format_money(row["amount_cents"]))}">'
                     f'{sign} {escape(format_money(row["amount_cents"]))}</div></div>')
    st.html('<div class="tx-list">' + ''.join(items) + '</div>')
