from io import BytesIO
import zipfile
import pytest
from openpyxl import load_workbook
from services.finance import create_account, create_transaction
from services.importing import (build_preview, export_csv, export_excel, import_preview,
                                read_csv, read_ofx, EXPORT_TABLES)


@pytest.fixture
def refs(db):
    return db.execute("SELECT id FROM categories ORDER BY id").fetchone()[0], create_account(db, "Banco", "corrente")


def preview(db, refs, rows):
    return build_preview(db, rows, {"date":"Data", "description":"Descrição", "amount":"Valor"}, refs[1], refs[0], default_type="auto")


def test_csv_brl_preview_deduplication_and_repeat_import(db, refs):
    content = 'Data;Descrição;Valor\n01/11/2026;Mercado;-1.234,56\n01/11/2026;  MERCADO  ;-1.234,56\n02/11/2026;Salário;5.000,00\n'
    rows = read_csv(content.encode("utf-8-sig"))
    result = preview(db, refs, rows)
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    assert [r["duplicate"] for r in result] == [False, True, False]
    assert [r["type"] for r in result] == ["despesa", "despesa", "receita"]
    assert result[0]["amount_cents"] == 123456
    assert import_preview(db, result) == 2
    assert import_preview(db, result) == 0
    assert import_preview(db, result, include_duplicates=True) == 3


def test_detects_existing_manual_transactions_and_rechecks_before_commit(db, refs):
    rows = [{"Data":"01/11/2026", "Descrição":"Compra", "Valor":"-10,00"}]
    result = preview(db, refs, rows)
    create_transaction(db, "2026-11-01", "Compra", 1000, "despesa", refs[0], refs[1])
    assert import_preview(db, result) == 0
    assert preview(db, refs, rows)[0]["duplicate"]


def test_invalid_line_blocks_all_rows(db, refs):
    rows = [{"Data":"01/11/2026", "Descrição":"OK", "Valor":"10,00"},
            {"Data":"31/02/2026", "Descrição":"Inválido", "Valor":"1"}]
    result = preview(db, refs, rows)
    assert result[1]["errors"]
    with pytest.raises(ValueError, match="Corrija"):
        import_preview(db, result)
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_commit_revalidates_and_rolls_back_entire_batch(db, refs):
    result = preview(db, refs, [{"Data":"01/11/2026", "Descrição":"OK", "Valor":"10,00"},
                               {"Data":"02/11/2026", "Descrição":"Outra", "Valor":"20,00"}])
    result[1]["account_id"] = 999
    with pytest.raises(ValueError):
        import_preview(db, result)
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


@pytest.mark.parametrize("content", ["", "data;data\n1;2", "data;valor\n1", "data;valor\n1;2;3", "data;valor\n"])
def test_invalid_csv(content):
    with pytest.raises(ValueError):
        read_csv(content.encode())


def test_latin1_csv():
    assert read_csv("Nome;Valor\nSaúde;10\n".encode("latin-1"), encoding="latin-1")[0]["Nome"] == "Saúde"


def test_ofx_sgml_and_xml(db, refs):
    for closed in (False, True):
        xml = "<OFX><BANKTRANLIST><STMTTRN><DTPOSTED>20261101120000[-3:BRT]{}<TRNAMT>-12.34{}<FITID>123{}<NAME>Farmácia{}<MEMO>Cartão{}</STMTTRN></BANKTRANLIST></OFX>"
        close = ("</DTPOSTED>", "</TRNAMT>", "</FITID>", "</NAME>", "</MEMO>") if closed else ("",)*5
        # SGML values need line boundaries between unclosed tags, as real OFX emits.
        raw = xml.format(*close).encode()
        rows = read_ofx(raw)
        result = build_preview(db, rows, {"date":"date", "description":"description", "amount":"amount"},
                               refs[1], refs[0], default_type="auto", date_format="%Y-%m-%d")
        assert not result[0]["errors"]
        assert result[0]["amount_cents"] == 1234
        assert result[0]["type"] == "despesa"
        assert result[0]["date"] == "2026-11-01"


def test_all_table_exports_preserve_money_and_neutralize_formulas(db, refs):
    create_transaction(db, "2026-11-01", "=HYPERLINK(ruim)", 123456, "despesa", refs[0], refs[1])
    with zipfile.ZipFile(BytesIO(export_csv(db))) as archive:
        assert set(archive.namelist()) == {f"{t}.csv" for t in EXPORT_TABLES}
        content = archive.read("transactions.csv").decode("utf-8-sig")
        assert "1234,56" in content and "01/11/2026" in content
        assert "'=HYPERLINK" in content
    workbook = load_workbook(BytesIO(export_excel(db)))
    assert set(workbook.sheetnames) == set(EXPORT_TABLES)
    values = list(workbook["transactions"].values)
    assert "1234,56" in values[1]
    assert "'=HYPERLINK(ruim)" in values[1]
    assert all(cell.data_type != "f" for row in workbook["transactions"] for cell in row)


def test_preview_notes_validation_and_portuguese_date_error(db, refs):
    rows = [{"Data":"31/02/2026", "Descrição":"Data ruim", "Valor":"10"}]
    assert "Data inválida" in preview(db, refs, rows)[0]["errors"][0]
    rows = [{"Data":"01/11/2026", "Descrição":"OK", "Valor":"10", "Nota":"x" * 5001}]
    result = build_preview(db, rows, {"date":"Data", "description":"Descrição", "amount":"Valor", "notes":"Nota"}, refs[1], refs[0])
    assert "observação" in result[0]["errors"][0]


def test_ofx_errors_and_entity_decoding(db, refs):
    with pytest.raises(ValueError, match="Codificação"):
        read_ofx(b"\x81")
    with pytest.raises(ValueError, match="sem lançamentos"):
        read_ofx(b"<OFX></OFX>")
    raw = b"<OFX><STMTTRN><DTPOSTED>invalid<TRNAMT>bad<NAME>A &amp; B</STMTTRN></OFX>"
    rows = read_ofx(raw)
    assert rows[0]["description"] == "A & B"
    result = build_preview(db, rows, {"date":"date", "description":"description", "amount":"amount"}, refs[1], refs[0], date_format="%Y-%m-%d")
    assert result[0]["errors"]
    rows[0]["date"] = "2026-11-01"
    result = build_preview(db, rows, {"date":"date", "description":"description", "amount":"amount"}, refs[1], refs[0], date_format="%Y-%m-%d")
    assert result[0]["errors"]


def test_concurrent_imports_recheck_duplicates_under_write_lock(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    from database.core import get_connection, initialize
    from services import importing

    path = tmp_path / "concurrent_import.db"
    conn = get_connection(path)
    initialize(conn)
    refs = (conn.execute("SELECT id FROM categories LIMIT 1").fetchone()[0],
            create_account(conn, "Banco", "corrente"))
    prepared = preview(conn, refs, [{"Data":"01/11/2026", "Descrição":"Compra", "Valor":"-10,00"}])
    conn.close()
    ready = Barrier(2)
    original_existing = importing._existing

    def slow_existing(db):
        identities = original_existing(db)
        # Expõe a janela entre leitura e gravação; o lock deve cobrir ambas.
        sleep(0.05)
        return identities

    monkeypatch.setattr(importing, "_existing", slow_existing)

    def run():
        db = get_connection(path)
        try:
            ready.wait(timeout=5)
            return import_preview(db, prepared)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: run(), range(2)))
    assert sorted(counts) == [0, 1]
    conn = get_connection(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    finally:
        conn.close()


def test_excel_replaces_xml_control_characters_without_changing_csv_or_database(db, refs):
    import csv
    from io import StringIO
    from services.importing import _excel_text

    raw_description = "Compra\x00\x07\x0b\x0c\x1f\ufffe\uffff"
    raw_notes = "=FÓRMULA\x0b\nobservação\ttexto"
    content = StringIO(newline="")
    writer = csv.writer(content, delimiter=";")
    writer.writerow(("Data", "Descrição", "Valor", "Observação"))
    writer.writerow(("01/11/2026", raw_description, "-1.234,56", raw_notes))
    rows = read_csv(content.getvalue().encode("utf-8-sig"))
    result = build_preview(db, rows, {"date":"Data", "description":"Descrição", "amount":"Valor", "notes":"Observação"},
                           refs[1], refs[0], default_type="auto")
    assert not result[0]["errors"]
    assert import_preview(db, result) == 1
    stored = db.execute("SELECT description,notes,amount_cents FROM transactions").fetchone()
    assert tuple(stored) == (raw_description, raw_notes, 123456)
    with zipfile.ZipFile(BytesIO(export_csv(db))) as archive:
        exported = archive.read("transactions.csv").decode("utf-8-sig")
        assert raw_description in exported
        assert raw_notes in exported
        assert "1234,56" in exported
    workbook = load_workbook(BytesIO(export_excel(db)))
    values = next(workbook["transactions"].iter_rows(min_row=2, values_only=True))
    assert "Compra" + "\ufffd" * 7 in values
    assert "'=FÓRMULA\ufffd\nobservação\ttexto" in values
    assert "1234,56" in values
    assert all(cell.data_type != "f" for row in workbook["transactions"] for cell in row)
    assert db.execute("SELECT description FROM transactions").fetchone()[0] == raw_description
    assert _excel_text("A\ud800\udfffZ") == "A\ufffd\ufffdZ"
    assert _excel_text("A\tB\nC\rD") == "A\tB\nC\rD"
