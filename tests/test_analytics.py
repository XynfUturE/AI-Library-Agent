"""Librarian reporting: counters, top books, monthly volume."""

from datetime import datetime, timedelta

from agent import analytics
from agent.database import get_connection
from agent.tools import borrow_book


def backdate_due_date(
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


def test_dashboard_has_every_section(app_database):

    dashboard = analytics.get_dashboard()

    assert set(dashboard) == {
        "overview",
        "top_books",
        "categories",
        "monthly_loans",
        "purchase_suggestions",
    }

    assert dashboard["overview"]["title_count"] > 0


def test_new_loan_moves_the_counters(
    app_database,
    new_user,
    available_book,
):

    before = analytics.get_overview()

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    after = analytics.get_overview()

    assert after["loan_count"] == before["loan_count"] + 1
    assert after["active_loan_count"] == (
        before["active_loan_count"] + 1
    )
    assert after["available_count"] == (
        before["available_count"] - 1
    )


def test_overdue_loan_is_counted(
    app_database,
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    before = analytics.get_overview()["overdue_loan_count"]

    backdate_due_date(
        borrowed["loan_id"],
        datetime.now() - timedelta(days=3),
    )

    after = analytics.get_overview()["overdue_loan_count"]

    assert after == before + 1


def test_top_books_counts_the_loan(
    app_database,
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    titles = {
        entry["title"]: entry["loan_count"]
        for entry in analytics.get_top_books()
    }

    assert titles.get(available_book["title"], 0) >= 1


def test_monthly_loans_are_bucketed(
    app_database,
    new_user,
    available_book,
):

    borrowed = borrow_book(
        available_book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed

    buckets = analytics.get_monthly_loans()

    assert buckets, "a fresh loan must appear in a month bucket"

    assert months_are_sorted(buckets)


def months_are_sorted(buckets):

    months = [
        bucket["month"]
        for bucket in buckets
    ]

    return months == sorted(months)
