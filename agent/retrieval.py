"""Retrieval layer for the library catalogue (the "R" in RAG).

Each book is embedded once and stored in SQLite, so the agent can search
by meaning instead of exact keywords ("a book about writing better code"
still finds Clean Code).

Two embedders, same interface:

* local (default): a dependency-free hashed bag-of-words + character
  n-gram vector. Works offline, in tests, and without any API account.
* remote: any OpenAI-compatible embeddings endpoint. Enabled by setting
  EMBEDDING_API_KEY and EMBEDDING_MODEL.

The index records which embedder produced it, so switching embedders
rebuilds instead of comparing vectors from two different spaces.

ponytail: cross-lingual queries (a Chinese question against English book
descriptions) need the remote embedder - the local one only matches
shared tokens and character n-grams.

ponytail: the local embedder weights every feature equally, so a common
word ("writing") can outrank the more specific one. Add IDF weighting or
BM25, or switch to the remote embedder, if ranking quality matters more
than running with zero dependencies.
"""

import hashlib
import json
import math
import os
import re

from agent.database import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

VECTOR_DIM = 256

LOCAL_EMBEDDER = "local-hashed-256"

DEFAULT_LIMIT = 5

REMOTE_BATCH_SIZE = 32

# Fields that make up the document text for one book.
BOOK_FIELDS = (
    "title",
    "author",
    "description",
)

_TOKEN_PATTERN = re.compile(
    r"[0-9a-z\u4e00-\u9fff]+"
)

_NGRAM_SIZE = 4


# ============================================================
# EMBEDDER SELECTION
# ============================================================

def embedder_name():
    """
    Name of the embedder the index should be built with.
    """

    if (
        os.getenv("EMBEDDING_API_KEY")
        or
        os.getenv("EMBEDDING_MODEL")
    ):

        return "remote:" + os.getenv(
            "EMBEDDING_MODEL",
            "text-embedding-3-small"
        )

    return LOCAL_EMBEDDER


# ============================================================
# LOCAL VECTOR
# ============================================================

def _features(text):
    """
    Turn text into hashed features.

    Words carry the meaning, character n-grams absorb typos and
    partial words ("program" still matches "programmer").
    """

    words = _TOKEN_PATTERN.findall(
        str(text or "").lower()
    )

    features = list(words)

    for word in words:

        for start in range(
            len(word) - _NGRAM_SIZE + 1
        ):

            features.append(
                "g:" + word[start:start + _NGRAM_SIZE]
            )

    return features


def _local_vector(text):
    """
    Build one normalised vector without any external dependency.

    Signed hashing keeps two different features that collide on the
    same bucket from always reinforcing each other.
    """

    vector = [0.0] * VECTOR_DIM

    for feature in _features(text):

        digest = hashlib.blake2b(
            feature.encode("utf-8"),
            digest_size=8
        ).digest()

        value = int.from_bytes(
            digest,
            "big"
        )

        index = value % VECTOR_DIM

        sign = 1.0 if (value >> 8) & 1 else -1.0

        vector[index] += sign

    return _normalise(vector)


def _normalise(vector):
    """
    Scale a vector to unit length so cosine similarity is a dot
    product, and so vectors from either embedder compare the same way.
    """

    length = math.sqrt(
        sum(value * value for value in vector)
    )

    if length == 0.0:

        return vector

    return [value / length for value in vector]


# ============================================================
# EMBEDDING
# ============================================================

def embed_texts(texts):
    """
    Embed a batch of texts with the configured embedder.
    """

    texts = list(texts)

    if not texts:

        return []

    if embedder_name() == LOCAL_EMBEDDER:

        return [
            _local_vector(text)
            for text in texts
        ]

    # The openai client is already a project dependency: only the
    # account behind it changes.
    from openai import OpenAI

    client = OpenAI(
        api_key=(
            os.getenv("EMBEDDING_API_KEY")
            or
            os.getenv("DEEPSEEK_API_KEY")
        ),
        base_url=(
            os.getenv("EMBEDDING_BASE_URL")
            or
            "https://api.openai.com/v1"
        ),
    )

    model = os.getenv(
        "EMBEDDING_MODEL",
        "text-embedding-3-small"
    )

    vectors = []

    for start in range(
        0,
        len(texts),
        REMOTE_BATCH_SIZE
    ):

        batch = texts[start:start + REMOTE_BATCH_SIZE]

        response = client.embeddings.create(
            model=model,
            input=batch,
        )

        for item in response.data:

            vectors.append(
                _normalise(
                    list(item.embedding)
                )
            )

    return vectors


def cosine_similarity(left, right):
    """
    Cosine similarity of two normalised vectors.
    """

    if not left or not right:

        return 0.0

    return sum(
        a * b
        for a, b in zip(left, right)
    )


# ============================================================
# INDEX STORAGE
# ============================================================

def _read_meta(cursor, key):

    cursor.execute(
        """
        SELECT value
        FROM rag_meta
        WHERE key = ?
        """,
        (key,)
    )

    row = cursor.fetchone()

    return row["value"] if row else None


def _write_meta(cursor, key, value):

    cursor.execute(
        """
        INSERT INTO rag_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value)
    )


def _book_document(row):

    parts = []

    for field in BOOK_FIELDS:

        value = row[field]

        if value:

            parts.append(str(value))

    return " ".join(parts)


def _fingerprint(cursor):
    """
    Cheap signature of the catalogue + the embedder in use.

    A row count plus the total text length catches inserts, deletes and
    most edits with one aggregate query.

    ponytail: a length-preserving edit slips through; hash every row if
    the catalogue changes often.
    """

    cursor.execute(
        """
        SELECT
            COUNT(*) AS books,
            COALESCE(
                SUM(
                    LENGTH(title)
                    + LENGTH(COALESCE(author, ''))
                    + LENGTH(COALESCE(description, ''))
                ),
                0
            ) AS characters
        FROM books
        """
    )

    row = cursor.fetchone()

    return "{}|{}|{}".format(
        embedder_name(),
        row["books"],
        row["characters"],
    )


def ensure_index(force=False):
    """
    Build the vector index when it is missing or out of date.

    Returns True when the index was (re)built.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        fingerprint = _fingerprint(cursor)

        if (
            not force
            and
            _read_meta(cursor, "fingerprint") == fingerprint
        ):

            return False

        cursor.execute(
            """
            SELECT
                id,
                title,
                author,
                description
            FROM books
            ORDER BY id
            """
        )

        books = cursor.fetchall()

        documents = [
            _book_document(book)
            for book in books
        ]

        vectors = embed_texts(documents)

        cursor.execute(
            "DELETE FROM book_embeddings"
        )

        for book, vector in zip(books, vectors):

            cursor.execute(
                """
                INSERT INTO book_embeddings
                (
                    book_id,
                    embedder,
                    vector
                )
                VALUES (?, ?, ?)
                """,
                (
                    book["id"],
                    embedder_name(),
                    json.dumps(vector),
                )
            )

        _write_meta(
            cursor,
            "fingerprint",
            fingerprint
        )

        connection.commit()

        return True

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# SEARCH
# ============================================================

def semantic_search(query, limit=DEFAULT_LIMIT):
    """
    Return the books closest in meaning to the query.

    Results below zero similarity are dropped, so an unrelated question
    returns nothing instead of the least bad match.

    ponytail: every vector is scored on every query (fine for a
    catalogue of this size); move to an ANN index if the catalogue
    reaches tens of thousands of books.
    """

    text = " ".join(
        str(query or "").split()
    )

    if not text:

        return []

    ensure_index()

    query_vector = embed_texts([text])[0]

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                book_embeddings.vector AS vector,
                books.id AS id,
                books.title AS title,
                books.author AS author,
                books.available AS available,
                categories.name AS category
            FROM book_embeddings
            JOIN books
                ON books.id = book_embeddings.book_id
            LEFT JOIN categories
                ON categories.id = books.category_id
            """
        )

        scored = []

        for row in cursor.fetchall():

            vector = json.loads(
                row["vector"]
            )

            score = cosine_similarity(
                query_vector,
                vector
            )

            if score <= 0.0:

                continue

            scored.append(
                (
                    score,
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "author": row["author"],
                        "available": bool(row["available"]),
                        "category": row["category"],
                        "score": round(score, 4),
                    },
                )
            )

        scored.sort(
            key=lambda item: item[0],
            reverse=True
        )

        return [
            result
            for _, result in scored[:max(1, int(limit))]
        ]

    finally:

        connection.close()
