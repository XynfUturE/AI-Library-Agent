from datetime import datetime, timedelta

from agent.database import get_connection


# ============================================================
# LIBRARY POLICIES
# ============================================================

LOAN_PERIOD_DAYS = 14

RENEWAL_PERIOD_DAYS = 14

# A loan can be extended at most this many times.
MAX_RENEWALS = 2

FINE_PER_DAY_CENTS = 50

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Tool results are replayed into the LLM context on every later turn,
# so every listing is capped. Without a cap a single wide search would
# cost tokens for the rest of the conversation.
SEARCH_RESULT_LIMIT = 20

AVAILABLE_RESULT_LIMIT = 25


# ============================================================
# SAFE ERROR RESULT
# ============================================================

def safe_error_result(
    message,
    error=None,
    error_type="ToolError"
):
    """
    Create a safe dictionary for tool failures.

    Internal exception details are kept only in _debug_error.
    The normal UI should never display that field.
    """

    return {

        "success":
            False,

        "error_type":
            error_type,

        "message":
            message,

        "_debug_error":
            (
                repr(error)
                if error is not None
                else None
            )

    }


# ============================================================
# DATE HELPERS
# ============================================================

def format_datetime(value):
    """
    Format datetime using the library's standard format.
    """

    if not isinstance(
        value,
        datetime
    ):

        raise TypeError(
            "value must be a datetime object."
        )

    return value.strftime(
        DATETIME_FORMAT
    )


def parse_datetime(value):
    """
    Parse a datetime string safely.
    """

    if not value:
        return None

    if isinstance(
        value,
        datetime
    ):

        return value

    try:

        return datetime.strptime(
            str(value),
            DATETIME_FORMAT
        )

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# USER ID
# ============================================================

def resolve_user_id(user_id):
    """
    Validate a supplied authenticated user ID.

    There is intentionally no demo-user fallback.
    """

    if user_id is None:

        return None

    try:

        user_id = int(
            user_id
        )

    except (
        TypeError,
        ValueError
    ):

        return None

    if user_id <= 0:

        return None

    return user_id


def user_exists(user_id):
    """
    Return True only for an active user account.
    """

    resolved_user_id = resolve_user_id(
        user_id
    )

    if resolved_user_id is None:

        return False

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id

            FROM users

            WHERE id = ?

            AND status = 'active'

            LIMIT 1
            """,
            (
                resolved_user_id,
            )
        )

        return (
            cursor.fetchone()
            is not None
        )

    except Exception:

        return False

    finally:

        if connection is not None:

            connection.close()


def validate_authenticated_user(user_id):
    """
    Confirm that the supplied user exists and is active.
    """

    resolved_user_id = resolve_user_id(
        user_id
    )

    if resolved_user_id is None:

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "A valid user ID is required."

        }

    if not user_exists(
        resolved_user_id
    ):

        return {

            "success":
                False,

            "error_type":
                "AuthorizationError",

            "message":
                "User account not found or inactive."

        }

    return {

        "success":
            True,

        "user_id":
            resolved_user_id

    }


# ============================================================
# FINE CALCULATION
# ============================================================

def calculate_fine_amount(
    due_date,
    end_date=None
):
    """
    Calculate overdue days and fine amount.

    Fine:
        $0.50 per overdue calendar day.
    """

    if not due_date:

        return {

            "is_overdue":
                False,

            "late_days":
                0,

            "fine_amount_cents":
                0,

            "fine_amount":
                0.00

        }

    due_datetime = parse_datetime(
        due_date
    )

    if due_datetime is None:

        return {

            "is_overdue":
                False,

            "late_days":
                0,

            "fine_amount_cents":
                0,

            "fine_amount":
                0.00,

            "error":
                "Invalid due date."

        }

    if end_date is None:

        end_datetime = datetime.now()

    elif isinstance(
        end_date,
        datetime
    ):

        end_datetime = end_date

    else:

        end_datetime = parse_datetime(
            end_date
        )

    if end_datetime is None:

        return {

            "is_overdue":
                False,

            "late_days":
                0,

            "fine_amount_cents":
                0,

            "fine_amount":
                0.00,

            "error":
                "Invalid end date."

        }

    if end_datetime <= due_datetime:

        return {

            "is_overdue":
                False,

            "late_days":
                0,

            "fine_amount_cents":
                0,

            "fine_amount":
                0.00

        }

    late_days = (

        end_datetime.date()
        -
        due_datetime.date()

    ).days

    late_days = max(
        0,
        late_days
    )

    fine_amount_cents = (

        late_days
        *
        FINE_PER_DAY_CENTS

    )

    fine_amount = round(
        fine_amount_cents / 100,
        2
    )

    return {

        "is_overdue":
            True,

        "late_days":
            late_days,

        "fine_amount_cents":
            fine_amount_cents,

        "fine_amount":
            fine_amount

    }


# ============================================================
# SEARCH BOOKS
# ============================================================

def search_books(keyword):
    """
    Search books by title keyword.
    """

    if not isinstance(
        keyword,
        str
    ):

        return []

    keyword = keyword.strip()

    if not keyword:

        return []

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                title,
                author,
                available

            FROM books

            WHERE title LIKE ?
                OR author LIKE ?

            ORDER BY id

            LIMIT ?
            """,
            (
                f"%{keyword}%",
                f"%{keyword}%",
                SEARCH_RESULT_LIMIT,
            )
        )

        rows = cursor.fetchall()

        results = []

        for row in rows:

            results.append({

                "id":
                    row["id"],

                "title":
                    row["title"],

                "author":
                    row["author"],

                "available":
                    bool(
                        row["available"]
                    )

            })

        return results

    except Exception as error:

        return safe_error_result(

            "The book search could not be completed.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# CHECK BOOK AVAILABILITY
# ============================================================

def check_book_availability(book_id):
    """
    Check whether a book is available.
    """

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError
    ):

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "error":
                "Invalid book ID.",

            "message":
                "Book ID must be a valid number."

        }

    if book_id <= 0:

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "error":
                "Invalid book ID.",

            "message":
                "Book ID must be a positive number."

        }

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                title,
                author,
                available

            FROM books

            WHERE id = ?

            LIMIT 1
            """,
            (
                book_id,
            )
        )

        row = cursor.fetchone()

        if row is None:

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "error":
                    "Book not found.",

                "message":
                    "Book not found."

            }

        return {

            "success":
                True,

            "id":
                row["id"],

            "title":
                row["title"],

            "author":
                row["author"],

            "available":
                bool(
                    row["available"]
                )

        }

    except Exception as error:

        return safe_error_result(

            "The book availability could not be checked.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# BORROW BOOK
# ============================================================

def borrow_book(
    book_id,
    user_id
):
    """
    Borrow an available book for the authenticated user.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError
    ):

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a valid number."

        }

    if book_id <= 0:

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a positive number."

        }

    connection = None

    try:

        connection = get_connection()

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Find book
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                title,
                author,
                available

            FROM books

            WHERE id = ?

            LIMIT 1
            """,
            (
                book_id,
            )
        )

        book = cursor.fetchone()

        if book is None:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "Book not found."

            }

        # ----------------------------------------------------
        # Availability
        # ----------------------------------------------------

        if not bool(
            book["available"]
        ):

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "Book is already borrowed.",

                "book": {

                    "id":
                        book["id"],

                    "title":
                        book["title"],

                    "author":
                        book["author"],

                    "available":
                        False

                }

            }

        # ----------------------------------------------------
        # Existing active record
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                id

            FROM borrow_records

            WHERE book_id = ?

            AND returned_at IS NULL

            LIMIT 1
            """,
            (
                book_id,
            )
        )

        active_record = cursor.fetchone()

        if active_record is not None:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "An active borrowing record already exists."

            }

        # ----------------------------------------------------
        # Dates
        # ----------------------------------------------------

        borrowed_at = datetime.now()

        due_date = (

            borrowed_at
            +
            timedelta(
                days=LOAN_PERIOD_DAYS
            )

        )

        borrowed_at_text = format_datetime(
            borrowed_at
        )

        due_date_text = format_datetime(
            due_date
        )

        # ----------------------------------------------------
        # Update book
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE books

            SET available = 0

            WHERE id = ?

            AND available = 1
            """,
            (
                book_id,
            )
        )

        if cursor.rowcount != 1:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "The book is no longer available."

            }

        # ----------------------------------------------------
        # Insert loan
        # ----------------------------------------------------

        cursor.execute(
            """
            INSERT INTO borrow_records
            (
                user_id,
                book_id,
                book_title,
                borrowed_at,
                due_date,
                returned_at,
                fine_amount_cents,
                fine_paid,
                fine_paid_at
            )

            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                NULL,
                0,
                0,
                NULL
            )
            """,
            (
                user_id,
                book["id"],
                book["title"],
                borrowed_at_text,
                due_date_text
            )
        )

        loan_id = cursor.lastrowid

        connection.commit()

        return {

            "success":
                True,

            "message":
                "Book borrowed successfully.",

            "loan_id":
                loan_id,

            "user_id":
                user_id,

            "book": {

                "id":
                    book["id"],

                "title":
                    book["title"],

                "author":
                    book["author"],

                "available":
                    False

            },

            "borrowed_at":
                borrowed_at_text,

            "due_date":
                due_date_text,

            "loan_period_days":
                LOAN_PERIOD_DAYS

        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(

            "The borrowing operation could not be completed.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# RETURN BOOK
# ============================================================

def return_book(
    book_id,
    user_id
):
    """
    Return a book currently borrowed by the authenticated user.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError
    ):

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a valid number."

        }

    if book_id <= 0:

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a positive number."

        }

    connection = None

    try:

        connection = get_connection()

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                borrow_records.borrowed_at,
                borrow_records.due_date,
                books.title,
                books.author

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.book_id = ?

            AND borrow_records.user_id = ?

            AND borrow_records.returned_at IS NULL

            ORDER BY borrow_records.id DESC

            LIMIT 1
            """,
            (
                book_id,
                user_id
            )
        )

        record = cursor.fetchone()

        if record is None:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "AuthorizationError",

                "message":
                    "This book is not currently borrowed by your account."

            }

        now = datetime.now()

        returned_at_text = format_datetime(
            now
        )

        fine_result = calculate_fine_amount(
            record["due_date"],
            now
        )

        fine_amount_cents = fine_result[
            "fine_amount_cents"
        ]

        fine_amount = fine_result[
            "fine_amount"
        ]

        # ----------------------------------------------------
        # Make book available
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE books

            SET available = 1

            WHERE id = ?
            """,
            (
                book_id,
            )
        )

        if cursor.rowcount != 1:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "DatabaseError",

                "message":
                    "The book could not be marked as available."

            }

        # ----------------------------------------------------
        # Complete loan
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE borrow_records

            SET
                returned_at = ?,
                fine_amount_cents = ?,
                fine_paid = 0,
                fine_paid_at = NULL

            WHERE id = ?

            AND user_id = ?

            AND returned_at IS NULL
            """,
            (
                returned_at_text,
                fine_amount_cents,
                record["id"],
                user_id
            )
        )

        if cursor.rowcount != 1:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "DatabaseError",

                "message":
                    "The return operation could not be completed."

            }

        # ----------------------------------------------------
        # Promote the next reader in the hold queue
        # ----------------------------------------------------

        next_in_queue = promote_next_hold(
            cursor,
            record["book_id"],
            returned_at_text,
        )

        connection.commit()

        return {

            "success":
                True,

            "message":
                "Book returned successfully.",

            "user_id":
                user_id,

            "loan_id":
                record["id"],

            "book": {

                "id":
                    record["book_id"],

                "title":
                    record["title"],

                "author":
                    record["author"],

                "available":
                    True

            },

            "borrowed_at":
                record["borrowed_at"],

            "due_date":
                record["due_date"],

            "returned_at":
                returned_at_text,

            "is_overdue":
                fine_result["is_overdue"],

            "late_days":
                fine_result["late_days"],

            "fine_amount_cents":
                fine_amount_cents,

            "fine_amount":
                fine_amount,

            "fine_paid":
                False,

            "fine_status":
                (
                    "Unpaid"
                    if fine_amount > 0
                    else
                    "No Fine"
                ),

            "next_in_queue":
                next_in_queue

        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(

            "The return operation could not be completed.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# RENEW BOOK
# ============================================================

def renew_book(
    book_id,
    user_id
):
    """
    Extend the due date of an active loan.

    Only loans that are still within their due date can be renewed,
    and only MAX_RENEWALS times.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError
    ):

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a valid number."

        }

    connection = None

    try:

        connection = get_connection()

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                book_id,
                book_title,
                due_date,
                renewals

            FROM borrow_records

            WHERE book_id = ?
            AND user_id = ?
            AND returned_at IS NULL

            LIMIT 1
            """,
            (
                book_id,
                user_id,
            )
        )

        record = cursor.fetchone()

        if record is None:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "You have no active loan for this book."

            }

        due_datetime = parse_datetime(
            record["due_date"]
        )

        if due_datetime is None:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "DatabaseError",

                "message":
                    "The due date of this loan could not be read."

            }

        if calculate_fine_amount(
            record["due_date"]
        )["is_overdue"]:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "Overdue books cannot be renewed. "
                    "Please return the book and pay the fine."

            }

        renewals = int(
            record["renewals"]
            or
            0
        )

        if renewals >= MAX_RENEWALS:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "This loan has already been renewed "
                    f"{MAX_RENEWALS} times."

            }

        new_due_date_text = format_datetime(

            due_datetime
            +
            timedelta(
                days=RENEWAL_PERIOD_DAYS
            )

        )

        cursor.execute(
            """
            UPDATE borrow_records

            SET due_date = ?,
                renewals = renewals + 1

            WHERE id = ?
            """,
            (
                new_due_date_text,
                record["id"],
            )
        )

        if cursor.rowcount != 1:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "DatabaseError",

                "message":
                    "The loan could not be renewed."

            }

        connection.commit()

        return {

            "success":
                True,

            "message":
                "Book renewed successfully.",

            "user_id":
                user_id,

            "loan_id":
                record["id"],

            "book": {

                "id":
                    record["book_id"],

                "title":
                    record["book_title"]

            },

            "previous_due_date":
                format_datetime(
                    due_datetime
                ),

            "due_date":
                new_due_date_text,

            "renewals":
                renewals + 1,

            "renewals_left":
                MAX_RENEWALS - renewals - 1

        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(

            "The loan could not be renewed.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# DEMAND QUEUE (HOLDS + PURCHASE SUGGESTIONS)
#
# One table serves both kinds of demand:
#
#   kind = "hold"        the library owns it, every copy is out
#   kind = "suggestion"  the library does not own it (no book_id)
#
# status flow: waiting -> ready (book is back, held for that reader)
#                     -> cancelled (reader withdrew)
# ============================================================

MAX_TITLE_LENGTH = 200


def _clean_title(title):

    if not isinstance(
        title,
        str
    ):

        return ""

    return title.strip()[
        :MAX_TITLE_LENGTH
    ]


def _queue_position(cursor, book_id, hold_id):
    """1-based place in line, counting waiting and ready holds."""

    row = cursor.execute(
        """
        SELECT COUNT(*)

        FROM holds

        WHERE book_id = ?
        AND kind = 'hold'
        AND status IN ('waiting', 'ready')
        AND id <= ?
        """,
        (
            book_id,
            hold_id,
        )
    ).fetchone()

    return row[0] if row else 0


def _estimated_wait_days(cursor, book_id, position):
    """
    Rough wait: the days left on the current loan, plus one loan
    period for every reader still ahead in the queue.
    """

    if position > 1:

        return (position - 1) * LOAN_PERIOD_DAYS

    row = cursor.execute(
        """
        SELECT due_date

        FROM borrow_records

        WHERE book_id = ?
        AND returned_at IS NULL
        AND due_date IS NOT NULL

        ORDER BY due_date

        LIMIT 1
        """,
        (
            book_id,
        )
    ).fetchone()

    if row is None:

        return 0

    due_datetime = parse_datetime(
        row["due_date"]
    )

    if due_datetime is None:

        return 0

    return max(
        0,
        (
            due_datetime.date()
            -
            datetime.now().date()
        ).days
    )


def promote_next_hold(cursor, book_id, ready_at_text):
    """
    Mark the first waiting hold as ready.

    Called when a copy comes back, inside the same transaction as the
    return, so the queue and the shelf never disagree.
    """

    row = cursor.execute(
        """
        SELECT
            holds.id,
            holds.user_id,
            users.username

        FROM holds

        LEFT JOIN users
            ON users.id = holds.user_id

        WHERE holds.book_id = ?
        AND holds.kind = 'hold'
        AND holds.status = 'waiting'

        ORDER BY holds.id

        LIMIT 1
        """,
        (
            book_id,
        )
    ).fetchone()

    if row is None:

        return None

    cursor.execute(
        """
        UPDATE holds

        SET status = 'ready',
            ready_at = ?

        WHERE id = ?
        """,
        (
            ready_at_text,
            row["id"],
        )
    )

    return {
        "hold_id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"],
    }


def request_book(
    user_id,
    book_id=None,
    title=None,
):
    """
    Ask for one book and get the next step back.

    Three outcomes:

    - on the shelf   -> nothing to queue, the reader can borrow now
    - lent out       -> join the hold queue, with position and estimate
    - not in catalog -> record a purchase suggestion for the librarian
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    title_text = _clean_title(
        title
    )

    has_book_id = book_id not in (
        None,
        "",
        0,
        "0",
    )

    if not has_book_id and not title_text:

        return {
            "success": False,
            "error_type": "ValidationError",
            "message": "Provide a book id or a book title.",
        }

    if has_book_id:

        try:

            book_id = int(
                book_id
            )

        except (
            TypeError,
            ValueError,
        ):

            return {
                "success": False,
                "error_type": "ValidationError",
                "message": "Book ID must be a valid number.",
            }

    connection = None

    try:

        connection = get_connection()

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        cursor = connection.cursor()

        book = None

        if has_book_id:

            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    author,
                    available

                FROM books

                WHERE id = ?

                LIMIT 1
                """,
                (
                    book_id,
                )
            )

            book = cursor.fetchone()

            if book is None:

                connection.rollback()

                return {
                    "success": False,
                    "error_type": "BusinessRuleError",
                    "message": "Book not found.",
                }

        else:

            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    author,
                    available

                FROM books

                WHERE title LIKE ?

                ORDER BY id

                LIMIT 1
                """,
                (
                    f"%{title_text}%",
                )
            )

            book = cursor.fetchone()

        # ------------------------------------------------
        # Not in the catalog: purchase suggestion
        # ------------------------------------------------

        if book is None:

            duplicate = cursor.execute(
                """
                SELECT id

                FROM holds

                WHERE user_id = ?
                AND kind = 'suggestion'
                AND status = 'waiting'
                AND lower(book_title) = lower(?)

                LIMIT 1
                """,
                (
                    user_id,
                    title_text,
                )
            ).fetchone()

            if duplicate is not None:

                connection.rollback()

                return {
                    "success": True,
                    "kind": "suggestion",
                    "hold_id": duplicate["id"],
                    "title": title_text,
                    "duplicate": True,
                    "message": (
                        "This purchase suggestion is already "
                        "waiting for the librarian."
                    ),
                }

            cursor.execute(
                """
                INSERT INTO holds
                    (
                        user_id,
                        book_id,
                        book_title,
                        kind,
                        status,
                        created_at
                    )

                VALUES (?, NULL, ?, 'suggestion', 'waiting', ?)
                """,
                (
                    user_id,
                    title_text,
                    format_datetime(
                        datetime.now()
                    ),
                )
            )

            suggestion_id = cursor.lastrowid

            connection.commit()

            return {
                "success": True,
                "kind": "suggestion",
                "hold_id": suggestion_id,
                "title": title_text,
                "duplicate": False,
                "message": (
                    "The library does not own this title yet; "
                    "your suggestion was sent to the librarian."
                ),
            }

        book_summary = {
            "id": book["id"],
            "title": book["title"],
            "author": book["author"],
        }

        # ------------------------------------------------
        # Already borrowed by this reader
        # ------------------------------------------------

        active = cursor.execute(
            """
            SELECT id

            FROM borrow_records

            WHERE book_id = ?
            AND user_id = ?
            AND returned_at IS NULL

            LIMIT 1
            """,
            (
                book["id"],
                user_id,
            )
        ).fetchone()

        if active is not None:

            connection.rollback()

            return {
                "success": True,
                "kind": "already_borrowed",
                "book": book_summary,
                "message": "You already have this book on loan.",
            }

        reserved = cursor.execute(
            """
            SELECT id

            FROM holds

            WHERE book_id = ?
            AND kind = 'hold'
            AND status = 'ready'

            LIMIT 1
            """,
            (
                book["id"],
            )
        ).fetchone()

        # ------------------------------------------------
        # On the shelf and nobody is waiting
        # ------------------------------------------------

        if bool(book["available"]) and reserved is None:

            connection.rollback()

            return {
                "success": True,
                "kind": "available",
                "book": book_summary,
                "message": (
                    "This book is on the shelf right now. "
                    "Ask me to borrow it."
                ),
            }

        # ------------------------------------------------
        # Join the queue
        # ------------------------------------------------

        duplicate_hold = cursor.execute(
            """
            SELECT id

            FROM holds

            WHERE user_id = ?
            AND book_id = ?
            AND kind = 'hold'
            AND status IN ('waiting', 'ready')

            LIMIT 1
            """,
            (
                user_id,
                book["id"],
            )
        ).fetchone()

        if duplicate_hold is not None:

            position = _queue_position(
                cursor,
                book["id"],
                duplicate_hold["id"],
            )

            wait_days = _estimated_wait_days(
                cursor,
                book["id"],
                position,
            )

            connection.rollback()

            return {
                "success": True,
                "kind": "hold",
                "hold_id": duplicate_hold["id"],
                "book": book_summary,
                "queue_position": position,
                "estimated_wait_days": wait_days,
                "duplicate": True,
                "message": (
                    "You are already in the queue for this book."
                ),
            }

        cursor.execute(
            """
            INSERT INTO holds
                (
                    user_id,
                    book_id,
                    book_title,
                    kind,
                    status,
                    created_at
                )

            VALUES (?, ?, ?, 'hold', 'waiting', ?)
            """,
            (
                user_id,
                book["id"],
                book["title"],
                format_datetime(
                    datetime.now()
                ),
            )
        )

        hold_id = cursor.lastrowid

        position = _queue_position(
            cursor,
            book["id"],
            hold_id,
        )

        wait_days = _estimated_wait_days(
            cursor,
            book["id"],
            position,
        )

        connection.commit()

        return {
            "success": True,
            "kind": "hold",
            "hold_id": hold_id,
            "book": book_summary,
            "queue_position": position,
            "estimated_wait_days": wait_days,
            "duplicate": False,
            "message": (
                "The book is lent out; you joined the queue. "
                "You will be told when it is your turn."
            ),
        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(
            "The request could not be queued.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


def get_my_holds(user_id):
    """Active holds and purchase suggestions for one reader."""

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        rows = cursor.execute(
            """
            SELECT
                id,
                book_id,
                book_title,
                kind,
                status,
                created_at,
                ready_at

            FROM holds

            WHERE user_id = ?
            AND status IN ('waiting', 'ready')

            ORDER BY id DESC
            """,
            (
                user_id,
            )
        ).fetchall()

        holds = []

        for row in rows:

            entry = {
                "hold_id": row["id"],
                "title": row["book_title"],
                "kind": row["kind"],
                "status": row["status"],
                "created_at": row["created_at"],
                "ready_at": row["ready_at"],
            }

            if row["book_id"] is not None:

                entry["book_id"] = row["book_id"]

                entry["queue_position"] = _queue_position(
                    cursor,
                    row["book_id"],
                    row["id"],
                )

            holds.append(
                entry
            )

        return holds

    except Exception as error:

        return safe_error_result(
            "Your queue could not be retrieved.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


def cancel_hold(user_id, hold_id):
    """Withdraw one of the authenticated reader's own requests."""

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    try:

        hold_id = int(
            hold_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return {
            "success": False,
            "error_type": "ValidationError",
            "message": "Hold ID must be a valid number.",
        }

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE holds

            SET status = 'cancelled'

            WHERE id = ?
            AND user_id = ?
            AND status IN ('waiting', 'ready')
            """,
            (
                hold_id,
                user_id,
            )
        )

        if cursor.rowcount != 1:

            connection.rollback()

            return {
                "success": False,
                "error_type": "BusinessRuleError",
                "message": (
                    "No active request of yours matches that ID."
                ),
            }

        connection.commit()

        return {
            "success": True,
            "hold_id": hold_id,
            "message": "The request was withdrawn.",
        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(
            "The request could not be withdrawn.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# CURRENT BORROWED BOOKS
# ============================================================

def get_current_borrowed_books(
    user_id,
    overdue_only=False,
):
    """
    Return active loans for the authenticated user only.

    When overdue_only is True, rows that cannot possibly be
    overdue are filtered in SQL first so fine amounts are only
    calculated for the relevant subset.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        overdue_filter = ""

        if overdue_only:

            overdue_filter = """

            AND borrow_records.due_date < date('now', 'localtime')"""

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                books.author,
                borrow_records.borrowed_at,
                borrow_records.due_date

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.user_id = ?

            AND borrow_records.returned_at IS NULL
            """
            +
            overdue_filter
            +
            """
            ORDER BY borrow_records.due_date ASC
            """,
            (
                user_id,
            )
        )

        rows = cursor.fetchall()

        books = []

        now = datetime.now()

        for row in rows:

            fine_result = calculate_fine_amount(

                row["due_date"],

                now

            )

            books.append({

                "loan_id":
                    row["id"],

                "user_id":
                    row["user_id"],

                "book_id":
                    row["book_id"],

                "book_title":
                    row["book_title"],

                "author":
                    row["author"],

                "borrowed_at":
                    row["borrowed_at"],

                "due_date":
                    row["due_date"],

                "is_overdue":
                    fine_result["is_overdue"],

                "late_days":
                    fine_result["late_days"],

                "estimated_fine_amount":
                    fine_result["fine_amount"]

            })

        return books

    except Exception as error:

        return safe_error_result(

            "Your current borrowed books could not be retrieved.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# OVERDUE BOOKS
# ============================================================

def get_overdue_books(
    user_id
):
    """
    Return overdue active loans for the user.
    """

    books = get_current_borrowed_books(
        user_id,
        overdue_only=True,
    )

    if isinstance(
        books,
        dict
    ):

        return books

    return [

        book

        for book in books

        if book.get(
            "is_overdue",
            False
        )

    ]


# ============================================================
# BOOK LOAN DETAILS
# ============================================================

def get_book_loan_details(
    book_id,
    user_id
):
    """
    Return active or most recent returned loan belonging
    to the specified user.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError
    ):

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a valid number."

        }

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Active loan
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                books.author,
                borrow_records.borrowed_at,
                borrow_records.due_date

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.book_id = ?

            AND borrow_records.user_id = ?

            AND borrow_records.returned_at IS NULL

            ORDER BY borrow_records.id DESC

            LIMIT 1
            """,
            (
                book_id,
                user_id
            )
        )

        row = cursor.fetchone()

        if row is not None:

            fine_result = calculate_fine_amount(
                row["due_date"]
            )

            return {

                "success":
                    True,

                "loan_status":
                    "Active",

                "loan_id":
                    row["id"],

                "user_id":
                    row["user_id"],

                "book_id":
                    row["book_id"],

                "book_title":
                    row["book_title"],

                "author":
                    row["author"],

                "borrowed_at":
                    row["borrowed_at"],

                "due_date":
                    row["due_date"],

                "returned_at":
                    None,

                "is_overdue":
                    fine_result["is_overdue"],

                "late_days":
                    fine_result["late_days"],

                "fine_amount":
                    fine_result["fine_amount"],

                "fine_status":
                    (
                        "Estimated"
                        if fine_result[
                            "fine_amount"
                        ] > 0

                        else

                        "No Fine"
                    )

            }

        # ----------------------------------------------------
        # Latest returned loan
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                books.author,
                borrow_records.borrowed_at,
                borrow_records.due_date,
                borrow_records.returned_at,
                borrow_records.fine_amount_cents,
                borrow_records.fine_paid,
                borrow_records.fine_paid_at

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.book_id = ?

            AND borrow_records.user_id = ?

            AND borrow_records.returned_at IS NOT NULL

            ORDER BY borrow_records.id DESC

            LIMIT 1
            """,
            (
                book_id,
                user_id
            )
        )

        row = cursor.fetchone()

        if row is None:

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "No loan record was found for this book."

            }

        fine_amount = round(

            row["fine_amount_cents"]
            /
            100,

            2

        )

        # Reconstruct the actual historical overdue span
        # instead of returning a hard-coded zero.
        returned_datetime = parse_datetime(
            row["returned_at"]
        )

        due_datetime = parse_datetime(
            row["due_date"]
        )

        if (
            returned_datetime is not None
            and due_datetime is not None
        ):

            historical_late_days = (
                returned_datetime.date()
                - due_datetime.date()
            ).days

        else:

            historical_late_days = 0

        historical_late_days = max(
            historical_late_days,
            0
        )

        return {

            "success":
                True,

            "loan_status":
                "Returned",

            "loan_id":
                row["id"],

            "user_id":
                row["user_id"],

            "book_id":
                row["book_id"],

            "book_title":
                row["book_title"],

            "author":
                row["author"],

            "borrowed_at":
                row["borrowed_at"],

            "due_date":
                row["due_date"],

            "returned_at":
                row["returned_at"],

            "is_overdue":
                fine_amount > 0,

            "late_days":
                historical_late_days,

            "fine_amount":
                fine_amount,

            "fine_status":
                (
                    "Paid"
                    if row["fine_paid"]

                    else

                    (
                        "Unpaid"
                        if fine_amount > 0
                        else
                        "No Fine"
                    )
                ),

            "fine_paid_at":
                row["fine_paid_at"]

        }

    except Exception as error:

        return safe_error_result(

            "The loan details could not be retrieved.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# CALCULATE FINE
# ============================================================

def calculate_fine(
    book_id,
    user_id
):
    """
    Calculate current or final fine for one user-owned loan.
    """

    loan = get_book_loan_details(
        book_id,
        user_id
    )

    if not isinstance(
        loan,
        dict
    ):

        return {

            "success":
                False,

            "error_type":
                "ToolError",

            "message":
                "Unable to calculate fine."

        }

    if loan.get(
        "success"
    ) is False:

        return loan

    return {

        "success":
            True,

        "user_id":
            loan["user_id"],

        "book_id":
            loan["book_id"],

        "book_title":
            loan["book_title"],

        "loan_status":
            loan["loan_status"],

        "due_date":
            loan["due_date"],

        "returned_at":
            loan["returned_at"],

        "is_overdue":
            loan["is_overdue"],

        "late_days":
            loan["late_days"],

        "fine_amount":
            loan["fine_amount"],

        "fine_status":
            loan["fine_status"],

        "fine_paid_at":
            loan.get(
                "fine_paid_at"
            )

    }


# ============================================================
# UNPAID FINES
# ============================================================

def get_unpaid_fines(
    user_id
):
    """
    Return unpaid final fines belonging only to the user.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                books.author,
                borrow_records.borrowed_at,
                borrow_records.due_date,
                borrow_records.returned_at,
                borrow_records.fine_amount_cents

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.user_id = ?

            AND borrow_records.returned_at IS NOT NULL

            AND borrow_records.fine_amount_cents > 0

            AND borrow_records.fine_paid = 0

            ORDER BY borrow_records.returned_at DESC
            """,
            (
                user_id,
            )
        )

        rows = cursor.fetchall()

        fines = []

        for row in rows:

            amount = round(

                row["fine_amount_cents"]
                /
                100,

                2

            )

            fines.append({

                "loan_id":
                    row["id"],

                "user_id":
                    row["user_id"],

                "book_id":
                    row["book_id"],

                "book_title":
                    row["book_title"],

                "author":
                    row["author"],

                "borrowed_at":
                    row["borrowed_at"],

                "due_date":
                    row["due_date"],

                "returned_at":
                    row["returned_at"],

                "fine_amount":
                    amount,

                "fine_status":
                    "Unpaid"

            })

        total_fine = round(

            sum(
                item["fine_amount"]
                for item in fines
            ),

            2

        )

        return {

            "success":
                True,

            "user_id":
                user_id,

            "fines":
                fines,

            "total_fine":
                total_fine

        }

    except Exception as error:

        return safe_error_result(

            "Your unpaid fines could not be retrieved.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# PAY FINE
# ============================================================

def pay_fine(
    book_id,
    user_id
):
    """
    Pay an unpaid final fine belonging to the authenticated user.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError
    ):

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "Book ID must be a valid number."

        }

    connection = None

    try:

        connection = get_connection()

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                books.author,
                borrow_records.returned_at,
                borrow_records.fine_amount_cents,
                borrow_records.fine_paid,
                borrow_records.fine_paid_at

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.book_id = ?

            AND borrow_records.user_id = ?

            AND borrow_records.returned_at IS NOT NULL

            AND borrow_records.fine_amount_cents > 0

            ORDER BY borrow_records.id DESC

            LIMIT 1
            """,
            (
                book_id,
                user_id
            )
        )

        record = cursor.fetchone()

        if record is None:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "No unpaid fine was found for this book."

            }

        if bool(
            record["fine_paid"]
        ):

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "BusinessRuleError",

                "message":
                    "This fine has already been paid.",

                "book": {

                    "id":
                        record["book_id"],

                    "title":
                        record["book_title"],

                    "author":
                        record["author"]

                },

                "fine_amount":
                    round(

                        record[
                            "fine_amount_cents"
                        ]
                        /
                        100,

                        2

                    ),

                "fine_paid_at":
                    record[
                        "fine_paid_at"
                    ]

            }

        fine_amount_cents = (

            record[
                "fine_amount_cents"
            ]

        )

        fine_amount = round(

            fine_amount_cents
            /
            100,

            2

        )

        payment_time = format_datetime(
            datetime.now()
        )

        cursor.execute(
            """
            UPDATE borrow_records

            SET
                fine_paid = 1,
                fine_paid_at = ?

            WHERE id = ?

            AND user_id = ?

            AND fine_paid = 0
            """,
            (
                payment_time,
                record["id"],
                user_id
            )
        )

        if cursor.rowcount != 1:

            connection.rollback()

            return {

                "success":
                    False,

                "error_type":
                    "DatabaseError",

                "message":
                    "The fine could not be paid."

            }

        connection.commit()

        return {

            "success":
                True,

            "message":
                "Fine paid successfully.",

            "user_id":
                user_id,

            "loan_id":
                record["id"],

            "book": {

                "id":
                    record["book_id"],

                "title":
                    record["book_title"],

                "author":
                    record["author"]

            },

            "fine_amount":
                fine_amount,

            "payment_amount":
                fine_amount,

            "fine_paid":
                True,

            "fine_paid_at":
                payment_time,

            "payment_status":
                "Paid"

        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(

            "The payment could not be completed.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# BORROWING HISTORY
# ============================================================

def get_borrow_history(
    user_id
):
    """
    Return borrowing history for the authenticated user only.
    """

    validation = validate_authenticated_user(
        user_id
    )

    if not validation["success"]:

        return validation

    user_id = validation["user_id"]

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                books.author,
                borrow_records.borrowed_at,
                borrow_records.due_date,
                borrow_records.returned_at,
                borrow_records.fine_amount_cents,
                borrow_records.fine_paid,
                borrow_records.fine_paid_at

            FROM borrow_records

            JOIN books
                ON books.id =
                    borrow_records.book_id

            WHERE borrow_records.user_id = ?

            ORDER BY borrow_records.borrowed_at DESC
            """,
            (
                user_id,
            )
        )

        rows = cursor.fetchall()

        history = []

        for row in rows:

            fine_amount = round(

                row[
                    "fine_amount_cents"
                ]
                /
                100,

                2

            )

            history.append({

                "loan_id":
                    row["id"],

                "user_id":
                    row["user_id"],

                "book_id":
                    row["book_id"],

                "book_title":
                    row["book_title"],

                "author":
                    row["author"],

                "borrowed_at":
                    row["borrowed_at"],

                "due_date":
                    row["due_date"],

                "returned_at":
                    row["returned_at"],

                "fine_amount":
                    fine_amount,

                "fine_paid":
                    bool(
                        row["fine_paid"]
                    ),

                "fine_paid_at":
                    row["fine_paid_at"]

            })

        return history

    except Exception as error:

        return safe_error_result(

            "Your borrowing history could not be retrieved.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# AVAILABLE BOOKS
# ============================================================

def list_available_books():

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                title,
                author

            FROM books

            WHERE available = 1

            ORDER BY id

            LIMIT ?
            """,
            (
                AVAILABLE_RESULT_LIMIT,
            )
        )

        rows = cursor.fetchall()

        books = []

        for row in rows:

            books.append({

                "id":
                    row["id"],

                "title":
                    row["title"],

                "author":
                    row["author"]

            })

        return books

    except Exception as error:

        return safe_error_result(

            "The available book list could not be retrieved.",

            error,

            "DatabaseError"

        )

    finally:

        if connection is not None:

            connection.close()
