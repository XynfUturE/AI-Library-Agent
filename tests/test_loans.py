"""Borrow / return / fine / payment state machine."""

from agent.auth import register_user
from agent.database import get_connection
from agent.tools import (
    borrow_book,
    get_current_borrowed_books,
    pay_fine,
    return_book,
)


def test_borrow_then_return(new_user, available_book):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    loans = get_current_borrowed_books(
        new_user["id"]
    )

    assert not (
        isinstance(loans, dict)
        and
        loans.get("success") is False
    ), loans

    returned = return_book(
        available_book["id"],
        new_user["id"],
    )

    assert returned["success"] is True, returned
    assert returned["is_overdue"] is False
    assert returned["fine_amount_cents"] == 0


def test_same_book_cannot_be_borrowed_twice(
    new_user,
    available_book,
):

    first = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert first["success"] is True, first

    second = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert second["success"] is False, second


def test_another_user_cannot_return_someone_elses_book(
    new_user,
    available_book,
    app_database,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    other = register_user(
        "intruder_" + str(new_user["id"]),
        "Passw0rd!23",
        "Other Reader",
    )

    assert other["success"] is True, other

    stolen_return = return_book(
        available_book["id"],
        other["user"]["id"],
    )

    assert stolen_return["success"] is False, stolen_return


def test_overdue_return_bills_once_and_payment_is_idempotent(
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    # Backdate the due date so the loan is unambiguously overdue.
    connection = get_connection()

    try:

        connection.execute(
            """
            UPDATE borrow_records
            SET due_date = ?
            WHERE id = ?
            """,
            (
                "2026-01-01 00:00:00",
                borrowed["loan_id"],
            )
        )

        connection.commit()

    finally:

        connection.close()

    returned = return_book(
        available_book["id"],
        new_user["id"],
    )

    assert returned["success"] is True, returned
    assert returned["is_overdue"] is True
    assert returned["fine_amount_cents"] > 0
    assert returned["fine_paid"] is False

    paid = pay_fine(
        available_book["id"],
        new_user["id"],
    )

    assert paid["success"] is True, paid
    assert paid["fine_paid"] is True

    paid_again = pay_fine(
        available_book["id"],
        new_user["id"],
    )

    assert paid_again["success"] is False, paid_again
