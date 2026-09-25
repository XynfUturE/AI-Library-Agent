"""Fine arithmetic is the money path: keep it pinned."""

from agent.tools import (
    FINE_PER_DAY_CENTS,
    calculate_fine_amount,
)


def test_missing_due_date_is_never_overdue():

    result = calculate_fine_amount(
        None
    )

    assert result["is_overdue"] is False
    assert result["fine_amount_cents"] == 0


def test_book_returned_before_due_date_costs_nothing():

    result = calculate_fine_amount(
        "2026-01-10 10:00:00",
        "2026-01-09 10:00:00",
    )

    assert result["is_overdue"] is False
    assert result["late_days"] == 0
    assert result["fine_amount_cents"] == 0


def test_overdue_days_are_billed_per_calendar_day():

    result = calculate_fine_amount(
        "2026-01-10 23:00:00",
        "2026-01-13 01:00:00",
    )

    assert result["is_overdue"] is True
    assert result["late_days"] == 3
    assert result["fine_amount_cents"] == 3 * FINE_PER_DAY_CENTS
    assert result["fine_amount"] == 1.5


def test_due_date_exactly_equal_to_end_date_is_not_overdue():

    result = calculate_fine_amount(
        "2026-01-10 10:00:00",
        "2026-01-10 10:00:00",
    )

    assert result["is_overdue"] is False
    assert result["fine_amount_cents"] == 0
