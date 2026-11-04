import pytest

from services.finance import (
    annual_summary, budget_status, category_spending, create_account, create_category,
    create_transaction, daily_spending, delete_account, delete_budget, delete_category,
    delete_transaction, get_transaction, list_accounts, list_categories, list_transactions,
    monthly_summary, set_budget, top_expenses, update_account, update_category, update_transaction,
)


@pytest.fixture
def setup(db):
    account = create_account(db, "Principal", "corrente", 10000)
    category = list_categories(db)[0]["id"]
    return account, category


def test_transaction_crud_updates_balance_exactly(db, setup):
    account, category = setup
    income = create_transaction(db, "2026-02-01", "Salário", 100001, "receita", category, account)
    expense = create_transaction(db, "2026-02-02", "Compra", 1999, "despesa", category, account, "nota")
    assert list_accounts(db)[0]["balance_cents"] == 108002
    update_transaction(db, expense, "2026-02-03", "Compra revisada", 2000, "despesa", category, account)
    assert get_transaction(db, expense)["description"] == "Compra revisada"
    assert list_accounts(db)[0]["balance_cents"] == 108001
    assert len(list_transactions(db, "2026-02")) == 2
    assert list_transactions(db, "2026-01") == []
    delete_transaction(db, expense)
    assert list_accounts(db)[0]["balance_cents"] == 110001
    delete_transaction(db, income)
    assert list_accounts(db)[0]["balance_cents"] == 10000


def test_credit_account_shows_debt_and_editing_account_moves_balance(db, setup):
    account, category = setup
    credit = create_account(db, "Cartão", "credito")
    id = create_transaction(db, "2026-02-01", "Mercado", 5000, "despesa", category, credit)
    balances = {a["id"]: a["balance_cents"] for a in list_accounts(db)}
    assert balances[credit] == -5000
    update_transaction(db, id, "2026-02-01", "Mercado", 5000, "despesa", category, account)
    balances = {a["id"]: a["balance_cents"] for a in list_accounts(db)}
    assert balances == {account: 5000, credit: 0}
    update_account(db, credit, "Cartão novo", "credito", -100)
    assert next(a for a in list_accounts(db) if a["id"] == credit)["balance_cents"] == -100
    delete_account(db, credit)
    with pytest.raises(ValueError, match="em uso"):
        delete_account(db, account)


@pytest.mark.parametrize("field,value", [
    ("date", "2026-02-30"), ("description", ""), ("amount_cents", 0),
    ("amount_cents", -10), ("amount_cents", 1.2), ("type", "transferencia"),
    ("category_id", 999), ("account_id", 999),
])
def test_transaction_validation_preserves_database(db, setup, field, value):
    account, category = setup
    args = dict(date="2026-02-01", description="Válida", amount_cents=100,
                type="despesa", category_id=category, account_id=account)
    args[field] = value
    with pytest.raises(ValueError):
        create_transaction(db, **args)
    assert list_transactions(db) == []


def test_categories_crud_and_reference_protection(db, setup):
    account, _ = setup
    id = create_category(db, "Pets")
    with pytest.raises(ValueError, match="em uso"):
        create_category(db, "pets")
    update_category(db, id, "Animais")
    transaction = create_transaction(db, "2026-02-01", "Ração", 5000, "despesa", id, account)
    with pytest.raises(ValueError, match="em uso"):
        delete_category(db, id)
    assert get_transaction(db, transaction)["category_name"] == "Animais"
    delete_transaction(db, transaction)
    delete_category(db, id)
    assert len(list_categories(db)) == 8


def test_dashboard_month_boundary_and_annual_totals(db, setup):
    account, category = setup
    for when, amount, kind in [("2025-12-31", 12000, "receita"),
                                ("2025-12-31", 2000, "despesa"),
                                ("2026-01-01", 20000, "receita"),
                                ("2026-01-02", 3000, "despesa"),
                                ("2026-01-02", 1500, "despesa"),
                                ("2026-02-01", 7777, "despesa")]:
        create_transaction(db, when, "Movimento", amount, kind, category, account)
    result = monthly_summary(db, "2026-01")
    assert result == dict(income_cents=20000, expense_cents=4500, balance_cents=15500,
                          previous_income_cents=12000, previous_expense_cents=2000,
                          previous_balance_cents=10000)
    assert category_spending(db, "2026-01")[0]["amount_cents"] == 4500
    daily = daily_spending(db, "2026-01")
    assert len(daily) == 31
    assert daily[0]["amount_cents"] == 0 and daily[1]["amount_cents"] == 4500
    assert len(daily_spending(db, "2024-02")) == 29
    assert [t["amount_cents"] for t in top_expenses(db, "2026-01")] == [3000, 1500]
    yearly = annual_summary(db, 2026)
    assert len(yearly) == 12 and yearly[0]["expense_cents"] == 4500
    assert yearly[1]["expense_cents"] == 7777 and yearly[2]["expense_cents"] == 0


def test_budget_thresholds_and_income_exclusion(db, setup):
    account, category = setup
    set_budget(db, "2026-02", category, 10000)
    create_transaction(db, "2026-02-01", "Salário", 99900, "receita", category, account)
    expense = create_transaction(db, "2026-02-02", "Compra", 7999, "despesa", category, account)
    assert budget_status(db, "2026-02")[0]["status"] == "normal"
    update_transaction(db, expense, "2026-02-02", "Compra", 8000, "despesa", category, account)
    assert budget_status(db, "2026-02")[0]["status"] == "atencao"
    update_transaction(db, expense, "2026-02-02", "Compra", 10000, "despesa", category, account)
    status = budget_status(db, "2026-02")[0]
    assert status["status"] == "excedido" and status["remaining_cents"] == 0
    update_transaction(db, expense, "2026-02-02", "Compra", 10001, "despesa", category, account)
    assert budget_status(db, "2026-02")[0]["remaining_cents"] == -1
    set_budget(db, "2026-02", category, 20000)
    assert len(budget_status(db, "2026-02")) == 1
    assert budget_status(db, "2026-02")[0]["status"] == "normal"
    assert budget_status(db, "2026-01") == []
    delete_budget(db, status["id"])
    assert budget_status(db, "2026-02") == []


def test_budget_protects_category_without_transactions(db):
    category = create_category(db, "Temporária")
    set_budget(db, "2026-01", category, 100)
    with pytest.raises(ValueError, match="em uso"):
        delete_category(db, category)


def test_empty_dashboard(db):
    assert monthly_summary(db, "2026-01")["balance_cents"] == 0
    assert category_spending(db, "2026-01") == []
    assert top_expenses(db, "2026-01") == []
