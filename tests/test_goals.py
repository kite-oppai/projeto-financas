import pytest
from services.finance import create_account, list_accounts
from services.goals import (add_contribution, create_goal, delete_contribution, delete_goal,
                            list_contributions, list_goals, update_goal)


def test_goal_progress_does_not_change_account_balance(db):
    create_account(db, "Banco", "corrente", 50000)
    id = create_goal(db, "Reserva", 10000, "2027-12-31")
    contribution = add_contribution(db, id, "2026-11-01", 3000, "Aporte")
    assert list_goals(db)[0]["saved_cents"] == 3000
    assert list_goals(db)[0]["remaining_cents"] == 7000
    assert list_goals(db)[0]["progress_percent"] == 30
    assert list_accounts(db)[0]["balance_cents"] == 50000
    assert list_contributions(db, id)[0]["notes"] == "Aporte"
    delete_contribution(db, contribution)
    assert list_goals(db)[0]["saved_cents"] == 0


def test_goal_edit_overfunding_and_delete_cascades(db):
    id = create_goal(db, "Viagem", 10000, "2027-12-31")
    add_contribution(db, id, "2026-11-01", 15000)
    update_goal(db, id, "Reserva", 12000, "2028-01-01")
    goal = list_goals(db)[0]
    assert goal["progress_percent"] == 100
    assert goal["remaining_cents"] == 0
    assert goal["saved_cents"] == 15000
    delete_goal(db, id)
    assert list_goals(db) == []
    assert db.execute("SELECT COUNT(*) FROM goal_contributions").fetchone()[0] == 0


@pytest.mark.parametrize("target,deadline", [(0,"2027-01-01"), (1.5,"2027-01-01"), (100,"2027-02-30")])
def test_goal_validation(db, target, deadline):
    with pytest.raises(ValueError):
        create_goal(db, "Meta", target, deadline)
    assert list_goals(db) == []


def test_contribution_notes_validation(db):
    id = create_goal(db, "Meta", 10000, "2027-01-01")
    for notes in (123, "x" * 5001):
        with pytest.raises(ValueError, match="observação"):
            add_contribution(db, id, "2026-11-01", 100, notes)
