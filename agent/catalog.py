import csv
from io import StringIO

from agent.database import get_connection

from agent.tools import (
    safe_error_result,
)


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _category_rows(cursor):
    """
    Return all categories ordered for tree building.
    """

    cursor.execute(
        """
        SELECT
            id,
            parent_id,
            name,
            sort_order
        FROM categories
        ORDER BY sort_order ASC, id ASC
        """
    )

    return cursor.fetchall()


def _category_maps(cursor):
    """
    Return (by_id, children_map) for two-level navigation.
    """

    by_id = {}

    children_map = {}

    for row in _category_rows(cursor):

        category_id = row["id"]

        by_id[category_id] = {
            "id": category_id,
            "parent_id": row["parent_id"],
            "name": row["name"],
            "sort_order": row["sort_order"],
        }

        parent_id = row["parent_id"]

        if parent_id is not None:

            children_map.setdefault(
                parent_id,
                []
            ).append(category_id)

    return by_id, children_map


def _subtree_ids(
    root_id,
    by_id,
    children_map,
):
    """
    Return a category id and all of its descendants.
    """

    if root_id not in by_id:

        return set()

    result = {root_id}

    stack = list(
        children_map.get(
            root_id,
            []
        )
    )

    while stack:

        category_id = stack.pop()

        if category_id in result:

            continue

        result.add(category_id)

        stack.extend(
            children_map.get(
                category_id,
                []
            )
        )

    return result


def _clean_text(value):
    """
    Normalise optional text fields to None when empty.
    """

    if value is None:

        return None

    if not isinstance(
        value,
        str
    ):

        value = str(value)

    value = value.strip()

    return value or None


def _category_label(
    category_id,
    by_id,
):
    """
    Build a readable path label such as
    "Computers & IT / Programming Languages".
    """

    if not category_id:

        return None

    segment = by_id.get(
        int(category_id)
    )

    if segment is None:

        return None

    names = [
        segment["name"]
    ]

    current = segment

    while current.get(
        "parent_id"
    ) is not None:

        parent = by_id.get(
            current["parent_id"]
        )

        if parent is None:

            break

        names.append(
            parent["name"]
        )

        current = parent

    names.reverse()

    return " / ".join(names)


def _serialize_book(
    row,
    by_id,
):
    """
    Convert a books row into a UI-ready catalog item.
    """

    if row is None:

        return None

    category_id = row["category_id"]

    return {
        "id":
            row["id"],

        "title":
            row["title"],

        "author":
            row["author"],

        "available":
            bool(
                row["available"]
            ),

        "category_id":
            category_id,

        "category_label":
            _category_label(
                category_id,
                by_id,
            ),

        "isbn":
            row["isbn"],

        "publisher":
            row["publisher"],

        "pub_date":
            row["pub_date"],

        "language":
            row["language"],

        "location":
            row["location"],

        "description":
            row["description"],

        "cover_url":
            row["cover_url"],
    }


def _find_book_row(
    cursor,
    book_id,
):
    """
    Fetch a single book row by id.
    """

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return None

    if book_id <= 0:

        return None

    cursor.execute(
        """
        SELECT
            id,
            title,
            author,
            available,
            category_id,
            isbn,
            publisher,
            pub_date,
            language,
            location,
            description,
            cover_url
        FROM books
        WHERE id = ?
        LIMIT 1
        """,
        (
            book_id,
        )
    )

    return cursor.fetchone()


def _category_exists(
    cursor,
    category_id,
):
    """
    Return True when the category id exists.
    """

    try:

        category_id = int(
            category_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return False

    cursor.execute(
        """
        SELECT id
        FROM categories
        WHERE id = ?
        LIMIT 1
        """,
        (
            category_id,
        )
    )

    return cursor.fetchone() is not None


def _isbn_exists(
    cursor,
    isbn,
    exclude_book_id=None,
):
    """
    Return True when the ISBN belongs to another book.
    """

    if not isbn:

        return False

    parameters = [isbn]

    exclusion = ""

    if exclude_book_id is not None:

        exclusion = "AND id != ?"

        parameters.append(
            exclude_book_id
        )

    cursor.execute(
        f"""
        SELECT id
        FROM books
        WHERE isbn = ?
        {exclusion}
        LIMIT 1
        """,
        parameters,
    )

    return cursor.fetchone() is not None


# ============================================================
# VALIDATION RESULT
# ============================================================

def validation_error(message):
    """
    Create a standard validation failure result.
    """

    return {
        "success":
            False,

        "error_type":
            "ValidationError",

        "message":
            message,
    }


# ============================================================
# CATEGORY TREE
# ============================================================

def get_catalog_categories():
    """
    Return the two-level category tree with book counts.
    """

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        # ------------------------------------------------
        # Total books
        # ------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM books
            """
        )

        total = cursor.fetchone()["count"]

        # ------------------------------------------------
        # Book count grouped by category
        # ------------------------------------------------

        cursor.execute(
            """
            SELECT
                category_id,
                COUNT(*) AS count
            FROM books
            GROUP BY category_id
            """
        )

        direct_counts = {
            row["category_id"]: row["count"]
            for row in cursor.fetchall()
        }

        # ------------------------------------------------
        # Category structure
        # ------------------------------------------------

        by_id, children_map = _category_maps(
            cursor
        )

        # ------------------------------------------------
        # Subtree counts (children add up into parents)
        # ------------------------------------------------

        def subtree_count(root_id):

            return sum(
                direct_counts.get(
                    child_id,
                    0,
                )
                for child_id in _subtree_ids(
                    root_id,
                    by_id,
                    children_map,
                )
            )

        # ------------------------------------------------
        # Build the visible tree
        # ------------------------------------------------

        categories = []

        for row in _category_rows(cursor):

            category_id = row["id"]

            if row["parent_id"] is not None:

                continue

            children = []

            for child_id in children_map.get(
                category_id,
                [],
            ):

                child = by_id[child_id]

                children.append({
                    "id":
                        child["id"],

                    "name":
                        child["name"],

                    "book_count":
                        subtree_count(
                            child_id
                        ),
                })

            categories.append({
                "id":
                    category_id,

                "name":
                    by_id[category_id]["name"],

                "book_count":
                    subtree_count(
                        category_id
                    ),

                "children":
                    children,
            })

        return {
            "success":
                True,

            "total":
                total,

            "categories":
                categories,
        }

    except Exception as error:

        return safe_error_result(
            "The catalog categories could not be retrieved.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# CATALOG QUERY (EXTENDED)
# ============================================================

def query_catalog(
    keyword=None,
    category_id=None,
    availability=None,
):
    """
    Query books with optional keyword, category subtree and
    availability filters.

    category_id selects the category subtree when given.
    """

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        by_id, children_map = _category_maps(
            cursor
        )

        conditions = []

        parameters = []

        # ------------------------------------------------
        # Keyword (title / author / ISBN / publisher)
        # ------------------------------------------------

        keyword = _clean_text(
            keyword
        )

        if keyword:

            conditions.append(
                """
                (
                    title LIKE ?
                    OR author LIKE ?
                    OR isbn LIKE ?
                    OR publisher LIKE ?
                )
                """
            )

            wildcard = f"%{keyword}%"

            parameters.extend(
                [
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                ]
            )

        # ------------------------------------------------
        # Category subtree
        # ------------------------------------------------

        if category_id is not None:

            try:

                category_id = int(
                    category_id
                )

            except (
                TypeError,
                ValueError,
            ):

                category_id = None

        if category_id is not None:

            if category_id in by_id:

                matching_ids = _subtree_ids(
                    category_id,
                    by_id,
                    children_map,
                )

                placeholders = ",".join(
                    "?" * len(matching_ids)
                )

                conditions.append(
                    f"category_id IN ({placeholders})"
                )

                parameters.extend(
                    sorted(
                        matching_ids
                    )
                )

            else:

                # Unknown category: nothing can match.
                return []

        # ------------------------------------------------
        # Availability
        # ------------------------------------------------

        if availability == "available":

            conditions.append(
                "available = 1"
            )

        elif availability == "loaned":

            conditions.append(
                "available = 0"
            )

        where_clause = (
            "WHERE "
            +
            " AND ".join(conditions)
        ) if conditions else ""

        cursor.execute(
            """
            SELECT
                id,
                title,
                author,
                available,
                category_id,
                isbn,
                publisher,
                pub_date,
                language,
                location,
                description,
                cover_url
            FROM books
            """
            +
            where_clause
            +
            """
            ORDER BY
                title COLLATE NOCASE ASC,
                id ASC
            """,
            parameters,
        )

        rows = cursor.fetchall()

        return [
            _serialize_book(
                row,
                by_id,
            )
            for row in rows
        ]

    except Exception as error:

        return safe_error_result(
            "The catalog could not be retrieved.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# VALIDATE BOOK FIELDS
# ============================================================

def validate_book_fields(
    fields,
):
    """
    Validate title/author/category_id/ISBN for a book payload.

    Returns (cleaned_fields, error_message).
    """

    cleaned = {}

    # ------------------------------------------------
    # Required text fields
    # ------------------------------------------------

    for key in (
        "title",
        "author",
    ):

        if key in fields:

            value = _clean_text(
                fields[key]
            )

            if not value:

                return (
                    None,
                    (
                        "Title and author "
                        "are required."
                    )
                )

            cleaned[key] = value

    # ------------------------------------------------
    # Optional text fields
    # ------------------------------------------------

    for key in (
        "isbn",
        "publisher",
        "pub_date",
        "language",
        "location",
        "cover_url",
        "description",
    ):

        if key in fields:

            cleaned[key] = _clean_text(
                fields[key]
            )

    # ------------------------------------------------
    # Availability
    # ------------------------------------------------

    if "available" in fields:

        value = fields["available"]

        cleaned["available"] = (
            1
            if value is True
            or value == 1
            or str(value).lower() == "true"
            else 0
        )

    return cleaned, None


# ============================================================
# CREATE BOOK (ADMIN)
# ============================================================

def create_book(
    fields,
):
    """
    Create one catalog book. category_id None leaves the book
    without a category.
    """

    cleaned, error = validate_book_fields(
        fields
    )

    if error:

        return validation_error(
            error
        )

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        # ------------------------------------------------
        # Validate category
        # ------------------------------------------------

        category_id = fields.get(
            "category_id"
        )

        if category_id in (None, "", 0, "0"):

            category_id = None

        else:

            if not _category_exists(
                cursor,
                category_id,
            ):

                return validation_error(
                    "The selected category does not exist."
                )

            category_id = int(
                category_id
            )

        cleaned["category_id"] = category_id

        # ------------------------------------------------
        # Validate ISBN uniqueness
        # ------------------------------------------------

        if cleaned.get(
            "isbn"
        ) and _isbn_exists(
            cursor,
            cleaned["isbn"],
        ):

            return validation_error(
                "A book with this ISBN already exists."
            )

        # ------------------------------------------------
        # Insert
        # ------------------------------------------------

        cursor.execute(
            """
            INSERT INTO books
            (
                title,
                author,
                available,
                category_id,
                isbn,
                publisher,
                pub_date,
                language,
                location,
                description,
                cover_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned["title"],
                cleaned["author"],
                cleaned.get(
                    "available",
                    1,
                ),
                cleaned["category_id"],
                cleaned.get(
                    "isbn",
                ),
                cleaned.get(
                    "publisher",
                ),
                cleaned.get(
                    "pub_date",
                ),
                cleaned.get(
                    "language",
                ),
                cleaned.get(
                    "location",
                ),
                cleaned.get(
                    "description",
                ),
                cleaned.get(
                    "cover_url",
                ),
            )
        )

        book_id = cursor.lastrowid

        connection.commit()

        by_id, _children = _category_maps(
            cursor
        )

        row = _find_book_row(
            cursor,
            book_id,
        )

        return {
            "success":
                True,

            "message":
                "Book added successfully.",

            "book":
                _serialize_book(
                    row,
                    by_id,
                ),
        }

    except Exception as error:

        connection.rollback()

        return safe_error_result(
            "The book could not be added.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# UPDATE BOOK (ADMIN)
# ============================================================

BOOK_EDITABLE_FIELDS = (
    "title",
    "author",
    "available",
    "category_id",
    "isbn",
    "publisher",
    "pub_date",
    "language",
    "location",
    "description",
    "cover_url",
)


def update_book(
    book_id,
    fields,
):
    """
    Update an existing catalog book.

    Only keys actually present in `fields` are changed, so a
    partial payload is safe. category_id=None clears it.
    """

    connection = None

    try:

        book_id = int(
            book_id
        )

    except (
        TypeError,
        ValueError,
    ):

        return validation_error(
            "A valid book ID is required."
        )

    if book_id <= 0:

        return validation_error(
            "A valid book ID is required."
        )

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        current = _find_book_row(
            cursor,
            book_id,
        )

        if current is None:

            return validation_error(
                "Book not found."
            )

        cleaned, error = validate_book_fields(
            fields
        )

        if error:

            return validation_error(
                error
            )

        allowed_fields = set(
            BOOK_EDITABLE_FIELDS
        )

        provided = set(
            fields.keys()
        ).intersection(
            allowed_fields
        )

        if not provided:

            return validation_error(
                "No editable fields were supplied."
            )

        # ------------------------------------------------
        # Category handling
        # ------------------------------------------------

        if "category_id" in fields:

            category_id = fields.get(
                "category_id"
            )

            if category_id in (None, "", 0, "0"):

                cleaned["category_id"] = None

            else:

                if not _category_exists(
                    cursor,
                    category_id,
                ):

                    return validation_error(
                        "The selected category does not exist."
                    )

                cleaned["category_id"] = int(
                    category_id
                )

        # ------------------------------------------------
        # ISBN uniqueness (excluding this book)
        # ------------------------------------------------

        isbn = cleaned.get(
            "isbn",
            fields.get(
                "isbn"
            ),
        )

        if isbn and _isbn_exists(
            cursor,
            isbn,
            exclude_book_id=book_id,
        ):

            return validation_error(
                "A book with this ISBN already exists."
            )

        # ------------------------------------------------
        # Build UPDATE
        # ------------------------------------------------

        update_parts = []

        parameters = []

        for key in sorted(
            provided
        ):

            if key == "category_id":

                value = cleaned.get(
                    "category_id"
                )

            else:

                value = cleaned.get(
                    key,
                    fields[key],
                )

            if key in ("available",):

                value = (
                    1
                    if value is True
                    or value == 1
                    or str(value).lower() == "true"
                    else 0
                )

            update_parts.append(
                f"{key} = ?"
            )

            parameters.append(
                value
            )

        parameters.append(
            book_id
        )

        cursor.execute(
            """
            UPDATE books
            SET
            """
            +
            ", ".join(update_parts)
            +
            """
            WHERE id = ?
            """,
            parameters,
        )

        connection.commit()

        by_id, _children = _category_maps(
            cursor
        )

        row = _find_book_row(
            cursor,
            book_id,
        )

        return {
            "success":
                True,

            "message":
                "Book updated successfully.",

            "book":
                _serialize_book(
                    row,
                    by_id,
                ),
        }

    except Exception as error:

        if connection is not None:

            connection.rollback()

        return safe_error_result(
            "The book could not be updated.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()


# ============================================================
# CSV IMPORT (ADMIN)
# ============================================================

# Normalised header -> internal column key
CSV_HEADER_MAP = {
    "title": "title",
    "book_title": "title",
    "author": "author",
    "category": "category_text",
    "category_name": "category_text",
    "category_id": "category_id",
    "isbn": "isbn",
    "isbn13": "isbn",
    "publisher": "publisher",
    "pub_date": "pub_date",
    "pubdate": "pub_date",
    "language": "language",
    "location": "location",
    "cover_url": "cover_url",
    "description": "description",
    "available": "available",
}

AVAILABLE_TRUE = {
    "1",
    "true",
    "yes",
    "y",
    "available",
}

AVAILABLE_FALSE = {
    "0",
    "false",
    "no",
    "n",
    "unavailable",
}


def _normalise_header(
    value,
):
    """
    Normalise a CSV header cell for matching.
    """

    return _clean_text(value)


def _resolve_category_text(
    text,
    by_id,
    children_map,
):
    """
    Resolve "Top / Child" or a plain name to a category id.
    """

    if not text:

        return None

    text = text.strip()

    # ------------------------------------------------
    # Numeric id
    # ------------------------------------------------

    if text.isdigit():

        category_id = int(text)

        if category_id in by_id:

            return category_id

        return None

    # ------------------------------------------------
    # Split path segments
    # ------------------------------------------------

    parts = [
        part.strip()
        for part in text.replace(
            "／",
            "/",
        ).split("/")
        if part.strip()
    ]

    top_name = parts[0]

    top_matches = [
        category_id
        for category_id, category in by_id.items()
        if category["parent_id"] is None
        and category["name"] == top_name
    ]

    if len(parts) == 1:

        if top_matches:

            return top_matches[0]

        # Also allow a bare leaf name.
        leaf_matches = [
            category_id
            for category_id, category in by_id.items()
            if category["parent_id"] is not None
            and category["name"] == text
        ]

        if leaf_matches:

            return leaf_matches[0]

        return None

    if not top_matches:

        return None

    top_id = top_matches[0]

    child_name = parts[1]

    for child_id in children_map.get(
        top_id,
        [],
    ):

        if by_id[child_id]["name"] == child_name:

            return child_id

    return None


def import_books_csv(
    csv_text,
):
    """
    Insert books from CSV text.

    Expected header example:

        title,author,category,isbn,publisher,pub_date,
        language,location,cover_url,description,available

    category accepts "Parent / Child" or a leaf/top name or id.
    available accepts 1/0, yes/no, true/false, available/unavailable.

    Rows that fail validation are skipped and reported per line.
    """

    # ------------------------------------------------
    # Basic text checks
    # ------------------------------------------------

    if not isinstance(
        csv_text,
        str,
    ) or not csv_text.strip():

        return validation_error(
            "No CSV content was provided."
        )

    content = csv_text.lstrip(
        "\ufeff"
    )

    try:

        rows = list(
            csv.reader(
                StringIO(
                    content
                )
            )
        )

    except csv.Error:

        return validation_error(
            "The CSV file could not be parsed."
        )

    if not rows:

        return validation_error(
            "The CSV file is empty."
        )

    # ------------------------------------------------
    # Parse header
    # ------------------------------------------------

    header = [
        _normalise_header(
            cell
        )
        for cell in rows[0]
    ]

    columns = [
        CSV_HEADER_MAP.get(
            cell
        )
        for cell in header
    ]

    if "title" not in columns or "author" not in columns:

        return validation_error(
            "CSV must start with a header row "
            "containing title and author columns."
        )

    data_rows = rows[1:]

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        by_id, children_map = _category_maps(
            cursor
        )

        # Pre-existing ISBNs for duplicate detection.
        cursor.execute(
            """
            SELECT isbn
            FROM books
            WHERE isbn IS NOT NULL
            """
        )

        known_isbns = {
            row["isbn"]
            for row in cursor.fetchall()
        }

        # ISBNs already seen earlier in this same file upload.
        seen_in_file_isbns = set()

        inserted = 0

        errors = []

        # ------------------------------------------------
        # Process each data row
        # ------------------------------------------------

        for index, raw_row in enumerate(data_rows, start=2):

            record = {}

            for column, value in zip(
                columns,
                raw_row,
            ):

                if column is None:

                    continue

                if column == "available":

                    record[column] = _clean_text(
                        value
                    ).lower() if _clean_text(
                        value
                    ) else None

                else:

                    record[column] = _clean_text(
                        value
                    )

            # --------------------------------------------
            # Required fields
            # --------------------------------------------

            if not record.get(
                "title"
            ) or not record.get(
                "author"
            ):

                errors.append({
                    "line": index,
                    "message":
                        "Title and author are required.",
                })

                continue

            # --------------------------------------------
            # Availability
            # --------------------------------------------

            available_text = record.get(
                "available"
            )

            if available_text is None:

                available = 1

            elif available_text in AVAILABLE_TRUE:

                available = 1

            elif available_text in AVAILABLE_FALSE:

                available = 0

            else:

                errors.append({
                    "line": index,
                    "message":
                        f"Unknown availability '{record['available']}'.",
                })

                continue

            # --------------------------------------------
            # Category
            # --------------------------------------------

            category_id = None

            if "category_id" in record and record.get(
                "category_id"
            ):

                raw_id = record["category_id"]

                if raw_id.isdigit():

                    parsed_id = int(
                        raw_id
                    )

                    if parsed_id in by_id:

                        category_id = parsed_id

                if category_id is None:

                    errors.append({
                        "line": index,
                        "message":
                            f"Category id '{raw_id}' not found.",
                    })

                    continue

            elif record.get(
                "category_text"
            ):

                category_id = _resolve_category_text(
                    record["category_text"],
                    by_id,
                    children_map,
                )

                if category_id is None:

                    errors.append({
                        "line": index,
                        "message":
                            "Category "
                            f"'{record['category_text']}' "
                            "not found.",
                    })

                    continue

            # --------------------------------------------
            # ISBN duplicate (database or file)
            # --------------------------------------------

            isbn = record.get(
                "isbn"
            )

            if isbn:

                if isbn in known_isbns:

                    errors.append({
                        "line": index,
                        "message":
                            "Duplicate ISBN "
                            f"'{isbn}'.",
                    })

                    continue

                if isbn in seen_in_file_isbns:

                    # A later identical row in this file.
                    errors.append({
                        "line": index,
                        "message":
                            "Duplicate ISBN "
                            f"'{isbn}'.",
                    })

                    continue

                # Remember the ISBN so later identical rows
                # are reported as duplicates too.
                seen_in_file_isbns.add(
                    isbn
                )

            # --------------------------------------------
            # Insert
            # --------------------------------------------

            cursor.execute(
                """
                INSERT INTO books
                (
                    title,
                    author,
                    available,
                    category_id,
                    isbn,
                    publisher,
                    pub_date,
                    language,
                    location,
                    description,
                    cover_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["title"],
                    record["author"],
                    available,
                    category_id,
                    isbn,
                    record.get(
                        "publisher"
                    ),
                    record.get(
                        "pub_date"
                    ),
                    record.get(
                        "language"
                    ),
                    record.get(
                        "location"
                    ),
                    record.get(
                        "description"
                    ),
                    record.get(
                        "cover_url"
                    ),
                )
            )

            if isbn:

                known_isbns.add(
                    isbn
                )

            inserted += 1

        connection.commit()

        return {
            "success":
                True,

            "message":
                (
                    f"Imported {inserted} of "
                    f"{len(data_rows)} books."
                ),

            "total_rows":
                len(data_rows),

            "inserted":
                inserted,

            "skipped":
                len(errors),

            "errors":
                errors,
        }

    except Exception as error:

        connection.rollback()

        return safe_error_result(
            "The CSV import could not be completed.",
            error,
            "DatabaseError",
        )

    finally:

        if connection is not None:

            connection.close()
