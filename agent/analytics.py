"""Reporting queries for the librarian dashboard.

Aggregates only: the numbers come from the same tables the circulation
tools write, so nothing has to be kept in sync.
"""

from datetime import datetime, timedelta

from agent.database import get_connection


DEFAULT_TOP_LIMIT = 10

DEFAULT_MONTHS = 6


def _scalar(cursor, query, parameters=()):

    row = cursor.execute(
        query,
        parameters,
    ).fetchone()

    return row[0] if row and row[0] is not None else 0


def get_overview():
    """Headline counters for the dashboard."""

    connection = get_connection()

    try:

        cursor = connection.cursor()

        return {
            "title_count": _scalar(
                cursor,
                "SELECT COUNT(*) FROM books",
            ),
            "available_count": _scalar(
                cursor,
                "SELECT COUNT(*) FROM books WHERE available = 1",
            ),
            "member_count": _scalar(
                cursor,
                "SELECT COUNT(*) FROM users WHERE status = 'active'",
            ),
            "active_loan_count": _scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM borrow_records
                WHERE returned_at IS NULL
                """,
            ),
            "overdue_loan_count": _scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM borrow_records
                WHERE returned_at IS NULL
                AND due_date IS NOT NULL
                AND due_date < ?
                """,
                (
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                ),
            ),
            "unpaid_fine_total": round(
                _scalar(
                    cursor,
                    """
                    SELECT SUM(fine_amount_cents)
                    FROM borrow_records
                    WHERE fine_paid = 0
                    AND fine_amount_cents > 0
                    """,
                )
                /
                100,
                2,
            ),
            "loan_count": _scalar(
                cursor,
                "SELECT COUNT(*) FROM borrow_records",
            ),
            "pending_hold_count": _scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM holds
                WHERE kind = 'hold'
                AND status IN ('waiting', 'ready')
                """,
            ),
            "pending_suggestion_count": _scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM holds
                WHERE kind = 'suggestion'
                AND status = 'waiting'
                """,
            ),
        }

    finally:

        connection.close()


def get_top_books(limit=DEFAULT_TOP_LIMIT):
    """Most borrowed titles, most popular first."""

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                book_id,
                book_title,
                COUNT(*) AS loan_count

            FROM borrow_records

            GROUP BY book_id, book_title

            ORDER BY loan_count DESC, book_title

            LIMIT ?
            """,
            (
                limit,
            )
        ).fetchall()

        return [
            {
                "book_id": row["book_id"],
                "title": row["book_title"],
                "loan_count": row["loan_count"],
            }
            for row in rows
        ]

    finally:

        connection.close()


def get_category_breakdown(limit=DEFAULT_TOP_LIMIT):
    """Loans per category."""

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                COALESCE(categories.name, 'Uncategorised') AS name,
                COUNT(*) AS loan_count

            FROM borrow_records

            LEFT JOIN books
                ON books.id = borrow_records.book_id

            LEFT JOIN categories
                ON categories.id = books.category_id

            GROUP BY name

            ORDER BY loan_count DESC, name

            LIMIT ?
            """,
            (
                limit,
            )
        ).fetchall()

        return [
            {
                "category": row["name"],
                "loan_count": row["loan_count"],
            }
            for row in rows
        ]

    finally:

        connection.close()


def get_monthly_loans(months=DEFAULT_MONTHS):
    """Loan volume per month, oldest first."""

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                substr(borrowed_at, 1, 7) AS month,
                COUNT(*) AS loan_count

            FROM borrow_records

            WHERE borrowed_at IS NOT NULL

            GROUP BY month

            ORDER BY month DESC

            LIMIT ?
            """,
            (
                months,
            )
        ).fetchall()

        return [
            {
                "month": row["month"],
                "loan_count": row["loan_count"],
            }
            for row in reversed(rows)
        ]

    finally:

        connection.close()


def get_purchase_suggestions(limit=DEFAULT_TOP_LIMIT):
    """
    The acquisition list: titles readers asked for that the
    library does not own, most requested first.
    """

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                MIN(book_title) AS title,
                COUNT(*) AS request_count,
                MAX(created_at) AS latest_at

            FROM holds

            WHERE kind = 'suggestion'
            AND status = 'waiting'

            GROUP BY lower(book_title)

            ORDER BY request_count DESC, title

            LIMIT ?
            """,
            (
                limit,
            )
        ).fetchall()

        return [
            {
                "title": row["title"],
                "request_count": row["request_count"],
                "latest_at": row["latest_at"],
            }
            for row in rows
        ]

    finally:

        connection.close()


def get_dashboard():
    """Everything the reporting view needs, in one call."""

    return {
        "overview": get_overview(),
        "top_books": get_top_books(),
        "categories": get_category_breakdown(),
        "monthly_loans": get_monthly_loans(),
        "purchase_suggestions": get_purchase_suggestions(),
    }
