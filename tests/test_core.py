from decimal import Decimal

import pytest

from database.core import initialize
from services.money import format_date, format_money, parse_money, validate_date, validate_month


def test_schema_migration_is_idempotent_and_does_not_recreate_deleted_categories(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM categories").fetchone()[0] == 8
    db.execute("DELETE FROM categories WHERE name='Outros'")
    db.commit()
    initialize(db)
    assert db.execute("SELECT count(*) FROM categories").fetchone()[0] == 7


@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", 123456), ("R$ 0,01", 1), ("-42,90", -4290),
    ("1234.56", 123456), (Decimal("10.12"), 1012), (15, 1500), ("0", 0),
])
def test_money_parses_exactly(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["", " ", "NaN", "Infinity", "1,234", "1.000.00", 1.1,
                                     True, "1e6", Decimal("NaN"), Decimal("0.001"), "1.23,45"])
def test_invalid_money_rejected(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


def test_portuguese_formatting():
    assert format_money(123456) == "R$ 1.234,56"
    assert format_money(-1) == "-R$ 0,01"
    assert format_date("2026-01-02") == "02/01/2026"


@pytest.mark.parametrize("value", ["2025-02-29", "2026-13-01", "2026-2-01", "hoje", ""])
def test_dates_rejected(value):
    with pytest.raises(ValueError):
        validate_date(value)


def test_month_validation():
    assert validate_month("2024-02") == "2024-02"
    with pytest.raises(ValueError):
        validate_month("2026-13")
