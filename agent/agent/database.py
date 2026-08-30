import os
import sqlite3


# ============================================================
# Database Path
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATABASE_DIR = os.path.join(
    BASE_DIR,
    "database"
)

DATABASE_PATH = os.path.join(
    DATABASE_DIR,
    "library.db"
)


# ============================================================
# Get Connection
# ============================================================

def get_connection():

    os.makedirs(
        DATABASE_DIR,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# Initialize Database
# ============================================================

def initialize_database():

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ====================================================
        # Books
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS books (

                id INTEGER PRIMARY KEY,

                title TEXT NOT NULL,

                author TEXT NOT NULL,

                available INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        # ====================================================
        # Borrow Records
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS borrow_records (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                book_id INTEGER NOT NULL,

                book_title TEXT NOT NULL,

                borrowed_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                due_date TIMESTAMP NULL,

                returned_at TIMESTAMP NULL
            )
            """
        )

        # ====================================================
        # Check Existing Columns
        # ====================================================

        cursor.execute(
            "PRAGMA table_info(borrow_records)"
        )

        columns = {
            row["name"]
            for row in cursor.fetchall()
        }

        # ====================================================
        # Migration: due_date
        # ====================================================

        if "due_date" not in columns:

            cursor.execute(
                """
                ALTER TABLE borrow_records
                ADD COLUMN due_date TIMESTAMP NULL
                """
            )

        # ====================================================
        # Migration: returned_at
        # ====================================================

        if "returned_at" not in columns:

            cursor.execute(
                """
                ALTER TABLE borrow_records
                ADD COLUMN returned_at TIMESTAMP NULL
                """
            )

        # ====================================================
        # Insert Demo Books
        # ====================================================

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM books
            """
        )

        row = cursor.fetchone()

        if row["count"] == 0:

            initial_books = [

                (
                    1,
                    "Python Programming",
                    "John Smith",
                    1
                ),

                (
                    2,
                    "Object-Oriented Design",
                    "Jane Brown",
                    0
                ),

                (
                    3,
                    "Database Systems",
                    "David Lee",
                    1
                )
            ]

            cursor.executemany(
                """
                INSERT INTO books
                (
                    id,
                    title,
                    author,
                    available
                )

                VALUES (?, ?, ?, ?)
                """,
                initial_books
            )

        # ====================================================
        # Repair Missing Due Dates
        #
        # Existing borrow records from the previous version
        # may not have a due_date.
        #
        # We leave them NULL rather than guessing a historical
        # date incorrectly.
        # ====================================================

        connection.commit()

    finally:

        connection.close()


# ============================================================
# Reset Demo Database
# ============================================================

def reset_demo_database():

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Reset demo book availability
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE books

            SET available = 1

            WHERE id = 1
            """
        )

        cursor.execute(
            """
            UPDATE books

            SET available = 0

            WHERE id = 2
            """
        )

        cursor.execute(
            """
            UPDATE books

            SET available = 1

            WHERE id = 3
            """
        )

        # ----------------------------------------------------
        # Clear test borrowing records
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM borrow_records
            """
        )

        # ----------------------------------------------------
        # Reset SQLite AUTOINCREMENT
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name = 'borrow_records'
            """
        )

        connection.commit()

    finally:

        connection.close()


# ============================================================
# Database Path
# ============================================================

def get_database_path():

    return DATABASE_PATH


# ============================================================
# Initialize on Import
# ============================================================

initialize_database()