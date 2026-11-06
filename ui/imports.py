"""Prévia obrigatória, mapeamento explícito e gravação confirmada de extratos."""
import hashlib
import json
import streamlit as st
from services.importing import read_csv, read_ofx, build_preview, import_preview, export_csv, export_excel
from services.money import format_money, format_date
from ui.common import require_catalogs, select_record, mutate, page_heading


def mapping_field(label, columns, key, aliases, optional=False):
    options = ([None] if optional else []) + columns
    suggestion = next((c for c in columns if c.strip().lower() in aliases), None)
    index = options.index(suggestion) if suggestion in options else 0
    return st.selectbox(label, options, index=index,
        format_func=lambda x: 'Não utilizar' if x is None else x, key=key)


def import_section(db):
    catalogs = require_catalogs(db)
    if not catalogs:
        return
    categories, accounts = catalogs
    st.caption('O arquivo é processado localmente. Escolha o destino, confira a prévia e confirme antes de salvar. Valores negativos podem identificar despesas no modo automático.')
    upload = st.file_uploader('Extrato CSV ou OFX', type=['csv', 'ofx'], key='import_file')
    if not upload:
        return
    data = upload.getvalue()
    if len(data) > 10 * 1024 * 1024:
        st.error('Use um arquivo de até 10 MB por importação.')
        return
    ofx = upload.name.lower().endswith('.ofx')
    if ofx:
        rows = read_ofx(data)
        mapping = {'date': 'date', 'description': 'description', 'amount': 'amount'}
        date_format = '%Y-%m-%d'
    else:
        with st.expander('Formato do CSV'):
            cols = st.columns(2)
            delimiter = cols[0].selectbox('Separador', [';', ',', '\t', '|'],
                format_func=lambda d: {';': 'Ponto e vírgula (;)', ',': 'Vírgula (,)', '\t': 'Tabulação', '|': 'Barra vertical (|)'}.get(d), key='csv_separator')
            encoding = cols[1].selectbox('Codificação', ['utf-8-sig', 'cp1252', 'latin-1'],
                format_func=lambda e: {'utf-8-sig': 'UTF-8', 'cp1252': 'Windows-1252', 'latin-1': 'Latin-1'}.get(e), key='csv_encoding')
        rows = read_csv(data, delimiter=delimiter, encoding=encoding)
        if not rows:
            st.warning('O arquivo não contém linhas de dados.')
            return
        columns = list(rows[0])
        st.subheader('Mapear colunas')
        mapping = {
            'date': mapping_field('Coluna de data', columns, 'csv_date', ['data', 'date']),
            'description': mapping_field('Coluna de descrição', columns, 'csv_description', ['descrição', 'descricao', 'description', 'histórico', 'historico']),
            'amount': mapping_field('Coluna de valor', columns, 'csv_amount', ['valor', 'amount', 'value']),
        }
        with st.expander('Colunas opcionais'):
            mapping['type'] = mapping_field('Coluna de tipo (opcional)', columns, 'csv_type', ['tipo', 'type'], optional=True)
            mapping['notes'] = mapping_field('Coluna de observação (opcional)', columns, 'csv_notes', ['observação', 'observacao', 'notes'], optional=True)
        mapping = {k: v for k, v in mapping.items() if v is not None}
        date_format = st.selectbox('Formato da data no arquivo', ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'],
            format_func=lambda f: {'%d/%m/%Y': 'dd/mm/aaaa', '%Y-%m-%d': 'aaaa-mm-dd', '%m/%d/%Y': 'mm/dd/aaaa'}.get(f), key='csv_date_format')
    if not rows:
        st.warning('Nenhuma transação encontrada no arquivo.')
        return
    account = select_record('Conta/cartão de destino', accounts, 'import_account')
    category = select_record('Categoria para os lançamentos deste arquivo', categories, 'import_category')
    default_type = st.selectbox('Tipo quando não informado na coluna', ['auto', 'despesa', 'receita'],
        format_func=lambda v: {'auto': 'Automático pelo sinal (− despesa, + receita)', 'despesa': 'Despesa', 'receita': 'Receita'}.get(v), key='import_type')
    signature = hashlib.sha256(data + json.dumps([rows, mapping, account, category, default_type, date_format], sort_keys=True).encode()).hexdigest()
    if st.button('Gerar prévia', type='primary'):
        preview = build_preview(db, rows, mapping, account, category, default_type=default_type, date_format=date_format)
        st.session_state['_import_preview'] = {'signature': signature, 'rows': preview}
        st.session_state['import_include_duplicates'] = False
        st.session_state['import_confirm_' + signature] = False
    saved = st.session_state.get('_import_preview')
    if not saved or saved['signature'] != signature:
        st.info('Gere a prévia após escolher o mapeamento e o destino.')
        return
    preview = saved['rows']
    errors = sum(bool(r['errors']) for r in preview)
    duplicates = sum(bool(r['duplicate']) for r in preview)
    st.subheader('Confira antes de salvar')
    st.write(f'{len(preview)} linhas · {duplicates} possíveis duplicatas · {errors} linhas com erro')
    st.dataframe([{'Linha': r['row_number'], 'Data': format_date(r['date']) if r.get('date') else '',
        'Descrição': r.get('description', ''), 'Valor': format_money(r['amount_cents']) if r.get('amount_cents') is not None else '',
        'Tipo': r.get('type', ''), 'Possível duplicata': 'Sim' if r['duplicate'] else 'Não',
        'Erros': '; '.join(r['errors'])} for r in preview], hide_index=True, width='stretch')
    include = st.checkbox('Incluir também as possíveis duplicatas', value=False, key='import_include_duplicates')
    confirmed = st.checkbox('Conferi a prévia e confirmo a gravação.', key='import_confirm_' + signature)
    if errors:
        st.error('Corrija as linhas com erro no arquivo e gere uma nova prévia. Nenhuma linha será salva enquanto houver erros.')
    if st.button('Salvar importação', disabled=bool(errors) or not confirmed, key='import_save'):
        def commit():
            count = import_preview(db, preview, include_duplicates=include)
            st.session_state.pop('_import_preview', None)
            st.session_state['_import_result_count'] = count
        mutate(commit, success='Importação concluída. Consulte os lançamentos no mês correspondente.')


def render(db, month):
    page_heading('Importar e exportar', 'Traga seu extrato ou guarde uma cópia dos seus registros.')
    imported_count = st.session_state.pop('_import_result_count', None)
    if imported_count is not None:
        st.info(f'{imported_count} lançamento(s) salvo(s). Duplicatas foram ignoradas, salvo inclusão explícita.')
    try:
        import_section(db)
    except ValueError as exc:
        st.error(str(exc))
    with st.expander('Exportar todos os dados'):
        st.caption('Inclui todo o histórico: lançamentos, categorias, contas, orçamentos, recorrências, metas e aportes. Guarde os arquivos em um local privado. Para restauração completa, use o backup do SQLite.')
        if st.button('Preparar arquivos para download'):
            st.session_state['_exports'] = {'csv': export_csv(db), 'excel': export_excel(db)}
        files = st.session_state.get('_exports')
        if files:
            st.caption('Os arquivos refletem os dados no momento da preparação. Prepare novamente após alterações.')
            st.download_button('Baixar CSVs (ZIP)', files['csv'], 'financas_csv.zip', mime='application/zip')
            st.download_button('Baixar Excel', files['excel'], 'financas.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
