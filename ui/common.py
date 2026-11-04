"""Composição da interface, com moeda brasileira e mensagens locais."""
import sqlite3
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
        st.rerun()


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
    fig.update_layout(margin=dict(l=8, r=8, t=32, b=8), font=dict(family='sans-serif'),
        legend_title_text='', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig
