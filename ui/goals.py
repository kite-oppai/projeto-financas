from datetime import date, timedelta
import streamlit as st
from services.goals import (list_goals, create_goal, update_goal, delete_goal,
    list_contributions, add_contribution, delete_contribution)
from services.money import format_money, format_date
from ui.common import amount_input, money_value, mutate, select_record, delete_control, page_heading, status_pill


def _close():
    st.session_state['goals_action'] = None


def fields(key, row=None):
    row = row or {}
    name = st.text_input('Nome da meta', value=row.get('name', ''), key=f'{key}_name')
    amount = amount_input('Valor-alvo (R$)', row.get('target_cents', 0), key=f'{key}_amount')
    deadline = st.date_input('Prazo', value=date.fromisoformat(row['deadline']) if row else date.today() + timedelta(days=365),
        format='DD/MM/YYYY', key=f'{key}_deadline')
    return name, amount, deadline


def save(function, db, values, selected=None):
    try:
        name, amount, deadline = values
        cents = money_value(amount)
    except ValueError as exc:
        st.error(str(exc))
        return
    args = [db] + ([selected] if selected is not None else []) + [name, cents, deadline]
    mutate(function, *args, success='Meta salva.')


def render(db, month):
    page_heading('Metas de economia', 'Cada aporte aproxima você do próximo objetivo.')
    rows = list_goals(db)
    for row in rows:
        with st.container():
            st.write(row['name'])
            st.caption('Prazo: ' + format_date(row['deadline']))
            st.write(f"{format_money(row['saved_cents'])} acumulados de {format_money(row['target_cents'])}")
            st.caption(f"Falta: {format_money(row['remaining_cents'])} · {row['progress_percent']}% do objetivo")
            if row['saved_cents'] >= row['target_cents']:
                status_pill('Objetivo alcançado!', 'success')
            elif row['deadline'] < date.today().isoformat():
                st.warning('Prazo encerrado. Você pode ajustar a meta ou continuar registrando aportes.')
    if not rows:
        st.info('Crie sua primeira meta para acompanhar uma reserva ou uma conquista.')
    options = ['Adicionar meta'] + (['Registrar aporte', 'Editar ou excluir', 'Excluir aporte'] if rows else [])
    action = st.selectbox('Gerenciar metas', options, index=None,
        placeholder='Escolha uma ação', key='goals_action')
    if action == 'Adicionar meta':
        with st.form('goal_new'):
            values = fields('new_goal')
            if st.form_submit_button('Criar meta', type='primary'):
                save(create_goal, db, values)
    elif action:
        selected = select_record('Meta', rows, 'goal_edit_id')
        row = next(r for r in rows if r['id'] == selected)
        if action == 'Registrar aporte':
            with st.form(f'contribution_new_{selected}'):
                when = st.date_input('Data do aporte', format='DD/MM/YYYY', key=f'contribution_date_{selected}')
                amount = amount_input('Valor do aporte (R$)', key=f'contribution_amount_{selected}')
                notes = st.text_input('Observação do aporte', key=f'contribution_notes_{selected}')
                if st.form_submit_button('Registrar aporte', type='primary'):
                    try:
                        cents = money_value(amount)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        mutate(add_contribution, db, selected, when, cents, notes=notes, success='Aporte registrado.')
        elif action == 'Editar ou excluir':
            with st.form(f'goal_edit_{selected}'):
                values = fields(f'edit_goal_{selected}', row)
                if st.form_submit_button('Salvar meta'):
                    save(update_goal, db, values, selected)
            st.caption('Excluir a meta também exclui seus registros de aportes.')
            delete_control('Excluir meta e aportes', f'del_goal_{selected}', delete_goal, db, selected)
        contributions = list_contributions(db, selected)
        if contributions and action in ('Registrar aporte', 'Excluir aporte'):
            st.caption('Histórico de aportes')
            st.dataframe([{'Data': format_date(r['date']), 'Valor': format_money(r['amount_cents']),
                'Observação': r.get('notes', '')} for r in contributions], hide_index=True, width='stretch')
        if action == 'Excluir aporte' and contributions:
            labels = {r['id']: f"{format_date(r['date'])} · {format_money(r['amount_cents'])} · {r.get('notes', '')}" for r in contributions}
            contribution = st.selectbox('Aporte', list(labels), format_func=labels.get, key=f'contribution_delete_id_{selected}')
            delete_control('Excluir aporte', f'del_contribution_{contribution}', delete_contribution, db, contribution)
        elif action == 'Excluir aporte':
            st.info('Esta meta ainda não tem aportes para excluir.')
    if action:
        st.button('Fechar formulário', key='goals_action_close', on_click=_close)
    with st.expander('Sobre os aportes'):
        st.write('Aportes são registros manuais para acompanhamento: não alteram os saldos das contas nem criam receitas ou despesas. Se houver movimentação financeira, registre-a também em Movimentos conforme seu controle.')
