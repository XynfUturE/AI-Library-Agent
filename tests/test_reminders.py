"""The due-date reminder listing and the renew business rules."""

from datetime import datetime, timedelta

from agent.database import get_connection
from agent.tools import (
    MAX_RENEWALS,
    borrow_book,
    renew_book,
)

from scripts.due_reminders import collect_due_loans


def set_due_date(
    loan_id,
    due_date,
):

    connection = get_connection()

    try:

        connection.execute(
            """
            UPDATE borrow_records
            SET due_date = ?
            WHERE id = ?
            """,
            (
                due_date.strftime("%Y-%m-%d %H:%M:%S"),
                loan_id,
            )
        )

        connection.commit()

    finally:

        connection.close()


def test_due_soon_loan_is_listed(new_user, available_book):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    now = datetime.now()

    set_due_date(
        borrowed["loan_id"],
        now + timedelta(days=1),
    )

    reminders = collect_due_loans(
        days=3,
        now=now,
    )

    listed = [
        item
        for item in reminders
        if item["loan_id"] == borrowed["loan_id"]
    ]

    assert listed, reminders
    assert listed[0]["is_overdue"] is False


def test_loan_due_next_month_is_not_a_reminder(
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    now = datetime.now()

    set_due_date(
        borrowed["loan_id"],
        now + timedelta(days=30),
    )

    reminders = collect_due_loans(
        days=3,
        now=now,
    )

    assert [
        item
        for item in reminders
        if item["loan_id"] == borrowed["loan_id"]
    ] == []


def test_overdue_loan_is_listed_with_a_fine(
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    now = datetime.now()

    set_due_date(
        borrowed["loan_id"],
        now - timedelta(days=2),
    )

    overdue = [
        item
        for item in collect_due_loans(days=3, now=now)
        if item["loan_id"] == borrowed["loan_id"]
    ]

    assert overdue, "an overdue loan must be listed"
    assert overdue[0]["is_overdue"] is True
    assert overdue[0]["late_days"] == 2
    assert overdue[0]["fine_amount"] == 1.0


def test_renew_extends_the_due_date(new_user, available_book):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    original_due_date = datetime.now() + timedelta(days=14)

    set_due_date(
        borrowed["loan_id"],
        original_due_date,
    )

    renewed = renew_book(
        available_book["id"],
        new_user["id"],
    )

    assert renewed["success"] is True, renewed
    assert renewed["renewals"] == 1
    assert renewed["previous_due_date"] != renewed["due_date"]


def test_renew_is_limited(new_user, available_book):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    set_due_date(
        borrowed["loan_id"],
        datetime.now() + timedelta(days=14),
    )

    for _ in range(MAX_RENEWALS):

        result = renew_book(
            available_book["id"],
            new_user["id"],
        )

        assert result["success"] is True, result

    blocked = renew_book(
        available_book["id"],
        new_user["id"],
    )

    assert blocked["success"] is False, blocked


def test_overdue_loan_cannot_be_renewed(
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    set_due_date(
        borrowed["loan_id"],
        datetime.now() - timedelta(days=1),
    )

    blocked = renew_book(
        available_book["id"],
        new_user["id"],
    )

    assert blocked["success"] is False, blocked


def test_loan_of_another_user_cannot_be_renewed(
    new_user,
    available_book,
    app_database,
):

    from agent.auth import register_user

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    other = register_user(
        "renewer_" + str(new_user["id"]),
        "Passw0rd!23",
        "Other Reader",
    )

    assert other["success"] is True, other

    blocked = renew_book(
        available_book["id"],
        other["user"]["id"],
    )

    assert blocked["success"] is False, blocked
