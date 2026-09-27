"""The retrieval layer: index building, refresh and semantic ranking."""

import pytest

from agent import database
from agent.retrieval import (
    cosine_similarity,
    ensure_index,
    local_vector,
    semantic_search,
)


def count_embeddings(database_path):

    connection = database.get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT COUNT(*) AS count FROM book_embeddings"
        )

        return cursor.fetchone()["count"]

    finally:

        connection.close()


def count_books(database_path):

    connection = database.get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT COUNT(*) AS count FROM books"
        )

        return cursor.fetchone()["count"]

    finally:

        connection.close()


def test_local_vectors_are_normalised_and_compare_cleanly():

    left = local_vector("clean code and refactoring")

    identical = local_vector("clean code and refactoring")

    unrelated = local_vector("tropical rainforest birds")

    assert pytest.approx(
        cosine_similarity(left, identical),
        abs=1e-6
    ) == 1.0

    assert cosine_similarity(
        left,
        identical
    ) > cosine_similarity(
        left,
        unrelated
    )


def test_index_covers_every_seeded_book(app_database):

    ensure_index(
        force=True
    )

    assert count_embeddings(app_database) == count_books(
        app_database
    )


def test_semantic_search_matches_meaning_not_wording(app_database):

    # None of these words appear in the book's title, only its meaning
    # appears in the description.
    results = semantic_search(
        "how to write maintainable code"
    )

    assert results, "a description-only query must still match"

    assert "Clean Code" in results[0]["title"]

    assert results[0]["score"] > 0


def test_semantic_search_copes_with_a_partial_word(app_database):

    results = semantic_search(
        "programm"
    )

    assert results

    titles = " ".join(
        result["title"]
        for result in results
    )

    assert "Python Crash Course" in titles or "Pragmatic" in titles


def test_unrelated_queries_return_nothing_strong(app_database):

    results = semantic_search(
        "qqzzxx plugh wibble frobnicate"
    )

    assert [
        result
        for result in results
        if result["score"] >= 0.2
    ] == []


def test_index_is_reused_until_the_catalogue_changes(app_database):

    assert ensure_index() is False

    connection = database.get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO books
            (title, author, available, description)
            VALUES (?, ?, 1, ?)
            """,
            (
                "Retrieval Test Book",
                "Test Author",
                "A temporary title used to test index refresh.",
            )
        )

        book_id = cursor.lastrowid

        connection.commit()

    finally:

        connection.close()

    try:

        assert ensure_index() is True

        results = semantic_search(
            "test index refresh temporary title"
        )

        assert results

        assert results[0]["id"] == book_id

    finally:

        connection = database.get_connection()

        try:

            cursor = connection.cursor()

            cursor.execute(
                "DELETE FROM books WHERE id = ?",
                (book_id,)
            )

            connection.commit()

        finally:

            connection.close()

        # Leave the shared test database indexed as it was found.
        ensure_index(
            force=True
        )
