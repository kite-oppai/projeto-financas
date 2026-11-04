"""Conversões de fronteira. Dinheiro nunca passa por float."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_CENTS = 10**14  # Limite por valor; também mantém totais práticos dentro do SQLite.


def require_cents(value, positive=True):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("O valor deve ser informado em centavos inteiros.")
    if abs(value) > MAX_CENTS:
        raise ValueError("Valor acima do limite permitido.")
    if positive and value <= 0:
        raise ValueError("Informe um valor maior que zero.")
    return value


def parse_money(value):
    """Lê reais: 1.234,56, 1234,56 ou 1234.56; não aceita arredondamento."""
    if isinstance(value, (float, bool)) or not isinstance(value, (str, Decimal, int)):
        raise ValueError("Informe um valor monetário válido, como 1.234,56.")
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("R$"):
            raw = raw[2:].strip()
        if "," in raw:
            if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d{1,2}", raw):
                raise ValueError("Valor inválido. Use o formato 1.234,56.")
            raw = raw.replace(".", "").replace(",", ".")
        elif not re.fullmatch(r"[+-]?\d+(?:\.\d{1,2})?", raw):
            raise ValueError("Valor inválido. Use até duas casas decimais.")
        value = raw
    try:
        amount = Decimal(value)
        if not amount.is_finite() or abs(amount) > Decimal(MAX_CENTS) / 100:
            raise ValueError("Valor monetário inválido ou acima do limite.")
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise ValueError("Use no máximo duas casas decimais.")
        return require_cents(int(cents), positive=False)
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("Valor monetário inválido.") from exc


def format_money(cents):
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise ValueError("O valor deve estar em centavos inteiros.")
    sign = "-" if cents < 0 else ""
    reais, fraction = divmod(abs(cents), 100)
    grouped = f"{reais:,}".replace(",", ".")
    return f"{sign}R$ {grouped},{fraction:02d}"


def validate_date(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Data inválida.") from exc


def validate_month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("Mês inválido. Use AAAA-MM.")
    validate_date(value + "-01")
    return value


def format_date(value):
    return date.fromisoformat(validate_date(value)).strftime("%d/%m/%Y")


def clean_text(value, label="Campo"):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} não pode ficar vazio.")
    if len(value.strip()) > 500:
        raise ValueError(f"{label} deve ter no máximo 500 caracteres.")
    return value.strip()
