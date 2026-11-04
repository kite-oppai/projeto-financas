"""Importação com prévia e exportação local. Nenhuma operação de rede."""
import csv
from datetime import datetime
import hashlib
import html
from io import BytesIO, StringIO
import re
import sqlite3
import zipfile

from services.money import clean_text, format_date, parse_money, require_cents, validate_date
from services.finance import transaction_values


EXPORT_TABLES = (
    "categories", "accounts", "transactions", "budgets", "recurring_rules",
    "recurrence_runs", "goals", "goal_contributions",
)


def read_csv(data, delimiter=";", encoding="utf-8-sig"):
    """Lê como texto: zeros, datas e quantias permanecem intactos até a prévia."""
    if delimiter not in (";", ",", "\t", "|"):
        raise ValueError("Separador inválido.")
    try:
        content = data.decode(encoding) if isinstance(data, bytes) else str(data)
        reader = csv.DictReader(StringIO(content), delimiter=delimiter)
        columns = reader.fieldnames
        if not columns or any(not str(c).strip() for c in columns):
            raise ValueError("O CSV precisa ter um cabeçalho com os nomes das colunas.")
        if len(set(columns)) != len(columns):
            raise ValueError("O CSV contém nomes de coluna repetidos.")
        rows = list(reader)
        if not rows:
            raise ValueError("O arquivo não contém lançamentos.")
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("Há linhas com quantidade de colunas diferente do cabeçalho.")
        return rows
    except (UnicodeError, LookupError) as exc:
        raise ValueError("Não foi possível ler a codificação. Tente UTF-8 ou Latin-1.") from exc
    except csv.Error as exc:
        raise ValueError("CSV inválido. Confira o separador e as aspas.") from exc


def read_ofx(data):
    """Suporta extratos OFX bancários/cartão em SGML ou XML, sem extensões remotas."""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = data.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise ValueError("Codificação OFX inválida. Use UTF-8 ou Windows-1252.") from exc
    else:
        text = str(data)
    records = re.findall(r"<STMTTRN\b[^>]*>(.*?)</STMTTRN\s*>", text, flags=re.I | re.S)
    if not records:
        raise ValueError("OFX sem lançamentos STMTTRN reconhecíveis.")

    def field(record, tag):
        found = re.search(rf"<{tag}\b[^>]*>\s*([^<\r\n]*)", record, flags=re.I)
        return html.unescape(found.group(1).strip()) if found else ""

    rows = []
    for record in records:
        raw_date = field(record, "DTPOSTED")
        try:
            parsed_date = datetime.strptime(raw_date[:8], "%Y%m%d").date().isoformat()
        except ValueError:
            parsed_date = raw_date
        name, memo = field(record, "NAME"), field(record, "MEMO")
        rows.append({"date": parsed_date, "description": " — ".join(filter(None, (name, memo))),
                     "amount": field(record, "TRNAMT"), "external_id": field(record, "FITID")})
    return rows


def _identity(row):
    # Categoria e observação podem ser corrigidas sem esconder uma duplicata do extrato.
    return (row["date"], " ".join(row["description"].casefold().split()),
            row["amount_cents"], row["type"], row["account_id"])


def _key(row):
    return hashlib.sha256(repr(_identity(row)).encode("utf-8")).hexdigest()


def _existing(db):
    return {_identity(dict(row)) for row in db.execute(
        "SELECT date,description,amount_cents,type,account_id FROM transactions"
    )}


def _references(db, category_id, account_id):
    for table, id, label in (("categories", category_id, "Categoria"), ("accounts", account_id, "Conta")):
        if isinstance(id, bool) or not isinstance(id, int):
            raise ValueError(f"{label} inválida.")
        if db.execute(f"SELECT id FROM {table} WHERE id=?", (id,)).fetchone() is None:
            raise ValueError(f"{label} não encontrada.")


def build_preview(db, rows, mapping, account_id, category_id, default_type="despesa",
                  date_format="%d/%m/%Y"):
    """Normaliza e marca erros/duplicatas. Esta função nunca grava no banco."""
    if default_type not in ("auto", "receita", "despesa"):
        raise ValueError("Tipo padrão inválido.")
    if not rows:
        raise ValueError("Nenhum lançamento para importar.")
    for key in ("date", "description", "amount"):
        if not mapping.get(key) or any(mapping[key] not in row for row in rows):
            raise ValueError(f"Mapeie a coluna obrigatória: {key}.")
    _references(db, category_id, account_id)
    seen = _existing(db)
    preview = []
    for number, raw in enumerate(rows, 2):
        item = {"row_number": number, "date": "", "description": "", "amount_cents": 0,
                "type": "", "category_id": category_id, "account_id": account_id,
                "notes": "", "duplicate": False, "errors": [], "import_key": ""}
        try:
            try:
                item["date"] = validate_date(datetime.strptime(
                    str(raw[mapping["date"]]).strip(), date_format).date())
            except ValueError as exc:
                raise ValueError("Data inválida ou diferente do formato selecionado.") from exc
            item["description"] = clean_text(raw[mapping["description"]], "Descrição")
            signed_cents = parse_money(str(raw[mapping["amount"]]).strip())
            item["amount_cents"] = require_cents(abs(signed_cents))
            selected_type = str(raw.get(mapping.get("type"), "")).strip().casefold()
            if selected_type:
                aliases = {"crédito": "receita", "credito": "receita", "credit": "receita",
                           "débito": "despesa", "debito": "despesa", "debit": "despesa"}
                item["type"] = aliases.get(selected_type, selected_type)
            else:
                item["type"] = ("receita" if signed_cents > 0 else "despesa") if default_type == "auto" else default_type
            if item["type"] not in ("receita", "despesa"):
                raise ValueError("Tipo deve ser receita ou despesa.")
            item["notes"] = raw.get(mapping.get("notes"), "") or ""
            validated = transaction_values(db, item["date"], item["description"], item["amount_cents"],
                                           item["type"], category_id, account_id, item["notes"])
            item["notes"] = validated[-1]
            identity = _identity(item)
            item["duplicate"] = identity in seen
            item["import_key"] = _key(item)
            seen.add(identity)
        except (ValueError, TypeError, OverflowError) as exc:
            message = str(exc)
            if "does not match format" in message or "unconverted data" in message:
                message = "Data inválida ou diferente do formato selecionado."
            item["errors"].append(message or "Linha inválida.")
        preview.append(item)
    return preview


def import_preview(db, preview, include_duplicates=False):
    """Grava a prévia inteira atomicamente; duplicatas são ignoradas por padrão."""
    if not preview:
        raise ValueError("Gere a prévia antes de importar.")
    if any(row.get("errors") for row in preview):
        raise ValueError("Corrija as linhas inválidas e gere uma nova prévia antes de importar.")
    count = 0
    try:
        with db:
            # Reserva a escrita antes da leitura: duas abas não aprovam a mesma
            # linha simultaneamente com base no mesmo estado anterior do banco.
            if not db.in_transaction:
                db.execute("BEGIN IMMEDIATE")
            seen = _existing(db)
            for original in preview:
                row = dict(original)
                values = transaction_values(db, row["date"], row["description"], row["amount_cents"],
                                            row["type"], row["category_id"], row["account_id"], row.get("notes", ""))
                row.update(zip(("date", "description", "amount_cents", "type", "category_id", "account_id", "notes"), values))
                identity = _identity(row)
                if identity in seen and not include_duplicates:
                    continue
                db.execute("""INSERT INTO transactions
                    (date,description,amount_cents,type,category_id,account_id,notes,import_key)
                    VALUES (?,?,?,?,?,?,?,?)""", (row["date"], row["description"], row["amount_cents"],
                    row["type"], row["category_id"], row["account_id"], row["notes"], _key(row)))
                seen.add(identity)
                count += 1
    except sqlite3.IntegrityError as exc:
        raise ValueError("Não foi possível importar. Confira valores, categorias e contas.") from exc
    return count


def _export_value(column, value):
    if value is None:
        return ""
    if column.endswith("_cents"):
        sign = "-" if value < 0 else ""
        absolute = abs(value)
        return f"{sign}{absolute // 100},{absolute % 100:02d}"
    if column in ("date", "deadline"):
        return format_date(value)
    # Evita execução de fórmulas ao abrir texto financeiro em uma planilha.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _export_rows(db, table):
    cursor = db.execute(f"SELECT * FROM {table} ORDER BY rowid")
    columns = [column[0] for column in cursor.description]
    headings = [name.removesuffix("_cents") + "_reais" if name.endswith("_cents") else name for name in columns]
    values = [[_export_value(column, row[column]) for column in columns] for row in cursor]
    return headings, values


def export_csv(db):
    """ZIP com CSV UTF-8 BOM de todas as tabelas, inclusive metas e recorrências."""
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in EXPORT_TABLES:
            headings, values = _export_rows(db, table)
            content = StringIO(newline="")
            writer = csv.writer(content, delimiter=";")
            writer.writerow(headings)
            writer.writerows(values)
            archive.writestr(f"{table}.csv", content.getvalue().encode("utf-8-sig"))
    return output.getvalue()


# Excel usa XML 1.0: substituímos apenas na cópia exportada, preservando o banco.
_INVALID_XML_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _excel_text(value):
    return _INVALID_XML_TEXT.sub("\ufffd", value) if isinstance(value, str) else value


def export_excel(db):
    """Valores monetários textuais preservam centavos sem conversão a float."""
    from openpyxl import Workbook
    workbook = Workbook()
    workbook.remove(workbook.active)
    for table in EXPORT_TABLES:
        sheet = workbook.create_sheet(table)
        headings, values = _export_rows(db, table)
        sheet.append(headings)
        for row in values:
            sheet.append([_excel_text(value) for value in row])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cells in sheet.columns:
            sheet.column_dimensions[cells[0].column_letter].width = min(55, max(14, max(len(str(c.value or "")) for c in cells) + 2))
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
