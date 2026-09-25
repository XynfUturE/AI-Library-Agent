"""Catalog admin path: create, update, the availability invariant, CSV import."""

import uuid

from agent import catalog
from agent import database
from agent.database import get_connection
from agent.tools import (
    borrow_book,
    return_book,
)


def new_isbn():

    return "978" + uuid.uuid4().hex[:10]


def create_book(**overrides):

    fields = {
        "title": "Catalog Test " + uuid.uuid4().hex[:8],
        "author": "Test Author",
        "isbn": new_isbn(),
    }

    fields.update(
        overrides
    )

    result = catalog.create_book(
        fields
    )

    assert result["success"] is True, result

    return result["book"]


def set_available_directly(
    book_id,
    available,
):
    """Bypass the API to simulate a database that already drifted."""

    connection = get_connection()

    try:

        connection.execute(
            """
            UPDATE books
            SET available = ?
            WHERE id = ?
            """,
            (
                available,
                book_id,
            )
        )

        connection.commit()

    finally:

        connection.close()


def is_marked_available(book_id):
    """Read the cached flag itself.

    The available-books tool caps its result at 25 rows, so it cannot
    be used to assert anything about a book created by a test.
    """

    connection = get_connection()

    try:

        row = connection.execute(
            """
            SELECT available
            FROM books
            WHERE id = ?
            """,
            (
                book_id,
            )
        ).fetchone()

    finally:

        connection.close()

    return bool(
        row["available"]
    )


def test_create_book_is_searchable(app_database):

    book = create_book(
        title="Refactoring Legacy Code"
    )

    hits = catalog.query_catalog(
        keyword="Refactoring Legacy"
    )

    assert [
        item["id"]
        for item in hits
    ] == [
        book["id"]
    ]


def test_create_book_rejects_an_empty_title(app_database):

    result = catalog.create_book({
        "title": "   ",
        "author": "Test Author",
    })

    assert result["success"] is False
    assert result["error_type"] == "ValidationError"


def test_duplicate_isbn_is_rejected(app_database):

    book = create_book()

    duplicate = catalog.create_book({
        "title": "Another Title",
        "author": "Test Author",
        "isbn": book["isbn"],
    })

    assert duplicate["success"] is False
    assert "ISBN" in duplicate["message"]


def test_update_changes_a_field(app_database):

    book = create_book()

    result = catalog.update_book(
        book["id"],
        {
            "publisher": "New Publisher",
        },
    )

    assert result["success"] is True, result
    assert result["book"]["publisher"] == "New Publisher"


def test_update_rejects_unknown_book(app_database):

    result = catalog.update_book(
        999999,
        {
            "publisher": "Nobody",
        },
    )

    assert result["success"] is False


def test_borrowed_book_cannot_be_marked_available(
    app_database,
    new_user,
):
    """Regression: the admin API used to break the availability cache."""

    book = create_book()

    borrowed = borrow_book(
        book["id"],
        new_user["id"],
    )

    assert borrowed["success"] is True, borrowed
    assert is_marked_available(book["id"]) is False

    blocked = catalog.update_book(
        book["id"],
        {
            "available": True,
        },
    )

    assert blocked["success"] is False, blocked
    assert blocked["error_type"] == "ValidationError"
    assert is_marked_available(book["id"]) is False


def test_returned_book_can_be_marked_available(
    app_database,
    new_user,
):
    """The guard must not block the legitimate case."""

    book = create_book()

    assert borrow_book(
        book["id"],
        new_user["id"],
    )["success"] is True

    assert return_book(
        book["id"],
        new_user["id"],
    )["success"] is True

    result = catalog.update_book(
        book["id"],
        {
            "available": True,
        },
    )

    assert result["success"] is True, result


def test_startup_repairs_drifted_availability(
    app_database,
    new_user,
):

    book = create_book()

    assert borrow_book(
        book["id"],
        new_user["id"],
    )["success"] is True

    # Simulate a row written before the guard existed.
    set_available_directly(
        book["id"],
        1,
    )

    assert is_marked_available(book["id"]) is True

    database.initialize_database()

    assert is_marked_available(book["id"]) is False


def test_csv_import_reports_bad_rows(app_database):

    good_title = "CSV Good " + uuid.uuid4().hex[:8]

    csv_text = (
        "title,author,publisher,available\n"
        f"{good_title},CSV Author,CSV Publisher,1\n"
        ",Missing Author,CSV Publisher,1\n"
    )

    result = catalog.import_books_csv(
        csv_text
    )

    assert result["success"] is True, result
    assert result["total_rows"] == 2
    assert result["inserted"] == 1
    assert result["skipped"] == 1
    assert result["errors"]

    hits = catalog.query_catalog(
        keyword=good_title
    )

    assert len(hits) == 1


def test_csv_import_rejects_empty_input(app_database):

    result = catalog.import_books_csv(
        "   "
    )

    assert result["success"] is False
