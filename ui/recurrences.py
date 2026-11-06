from datetime import date
import streamlit as st
from services.recurring import list_rules, create_rule, update_rule, delete_rule, generate_due
from services.money import format_money
from ui.common import amount_input, money_value, mutate, require_catalogs, select_record, delete_control, TYPES, page_heading


def _close():
    st.session_state['recurring_action'] = None


def fields(categories, accounts, key, row=None):
    row = row or {}
    description = st.text_input('Descrição', value=row.get('description', ''), key=f'{key}_description')
    amount = amount_input('Valor (R$)', row.get('amount_cents', 0), key=f'{key}_amount')
    types = list(TYPES)
    kind = st.selectbox('Tipo', types, index=types.index(row.get('type', 'despesa')), format_func=TYPES.get, key=f'{key}_type')
    category = select_record('Categoria', categories, f'{key}_category', selected=row.get('category_id'))
    account = select_record('Conta/cartão', accounts, f'{key}_account', selected=row.get('account_id'))
    day = st.number_input('Dia de vencimento', min_value=1, max_value=31, value=row.get('day', 1), step=1, key=f'{key}_day')
    start = st.date_input('Mês inicial (o dia será ignorado)',
        value=date.fromisoformat(row['start_month'] + '-01') if row else date.today(), format='DD/MM/YYYY', key=f'{key}_start')
    end = st.date_input('Mês final (opcional; o dia será ignorado)',
        value=date.fromisoformat(row['end_month'] + '-01') if row.get('end_month') else None,
        format='DD/MM/YYYY', key=f'{key}_end')
    active = st.checkbox('Recorrência ativa', value=bool(row.get('active', True)), key=f'{key}_active')
    notes = st.text_area('Observação', value=row.get('notes', ''), key=f'{key}_notes')
    return description, amount, kind, category, account, day, start, end, notes, active


def save(function, db, values, selected=None):
    try:
        description, amount, kind, category, account, day, start, end, notes, active = values
        cents = money_value(amount)
        if not start:
            raise ValueError('Informe o mês inicial.')
        start_month = start.strftime('%Y-%m')
        end_month = end.strftime('%Y-%m') if end else None
    except ValueError as exc:
        st.error(str(exc))
        return
    args = [db] + ([selected] if selected is not None else [])
    mutate(function, *args, description, cents, kind, category, account, day, start_month,
        end_month=end_month, notes=notes, active=active, success='Recorrência salva. Os vencimentos já atingidos serão gerados automaticamente.')


def render(db, month):
    page_heading('Recorrências', 'Seus compromissos e recebimentos mensais, sem repetir o cadastro.')
    catalogs = require_catalogs(db)
    if not catalogs:
        return
    categories, accounts = catalogs
    rows = list_rules(db)
    if rows:
        st.dataframe([{'Descrição': r['description'], 'Valor': format_money(r['amount_cents']),
            'Tipo': TYPES[r['type']], 'Dia': r['day'],
            'Ativa': 'Sim' if r['active'] else 'Não'} for r in rows], hide_index=True, width='stretch')
    else:
        st.info('Cadastre aluguel, assinaturas ou salário para gerar seus lançamentos mensais.')
    options = ['Adicionar recorrência'] + (['Editar ou excluir'] if rows else [])
    action = st.selectbox('Gerenciar recorrências', options, index=None,
        placeholder='Escolha uma ação', key='recurring_action')
    if action == 'Adicionar recorrência':
        with st.form('recurrence_new'):
            values = fields(categories, accounts, 'new_rule')
            if st.form_submit_button('Criar recorrência', type='primary'):
                save(create_rule, db, values)
    elif action == 'Editar ou excluir':
        st.caption('Editar, desativar ou excluir a regra preserva os lançamentos já gerados. Para cancelar um mês já gerado, exclua apenas seu lançamento na página Lançamentos.')
        selected = select_record('Recorrência', rows, 'recurrence_edit_id', name='description')
        row = next(r for r in rows if r['id'] == selected)
        with st.form(f'recurrence_edit_{selected}'):
            values = fields(categories, accounts, f'edit_rule_{selected}', row)
            if st.form_submit_button('Salvar recorrência'):
                save(update_rule, db, values, selected)
        delete_control('Excluir recorrência', f'del_rule_{selected}', delete_rule, db, selected)
    if action:
        st.button('Fechar formulário', key='recurring_action_close', on_click=_close)
    with st.expander('Como as recorrências funcionam'):
        st.write('Ao abrir ou interagir com o app, os vencimentos até hoje são gerados uma única vez, incluindo meses pendentes. Dias inexistentes, como 31 de fevereiro, usam o último dia do mês. O app precisa ser aberto para gerar lançamentos.')
        st.write('Reativar uma regra recupera também os meses pendentes durante a pausa. Para encerrar a obrigação, defina o mês final. Excluir uma ocorrência gerada não faz com que ela reapareça.')
    if rows:
        with st.expander('Ver detalhes das recorrências'):
            st.dataframe([{'Descrição': r['description'], 'Categoria': r['category_name'],
                'Conta/cartão': r['account_name'], 'Início': r['start_month'][5:] + '/' + r['start_month'][:4],
                'Fim': (r['end_month'][5:] + '/' + r['end_month'][:4]) if r['end_month'] else 'Sem fim',
                'Observação': r['notes']} for r in rows], hide_index=True, width='stretch')
