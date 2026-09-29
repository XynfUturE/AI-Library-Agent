import os
import sqlite3


# ============================================================
# DATABASE PATH
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

# LIBRARY_DB_PATH lets tests and deployments point the app at a
# different SQLite file without touching the source tree.
DATABASE_PATH = (
    os.getenv("LIBRARY_DB_PATH")
    or
    os.path.join(
        DATABASE_DIR,
        "library.db"
    )
)


# ============================================================
# GET CONNECTION
# ============================================================

def get_connection():
    """
    Create and return a new SQLite connection.

    Each operation should obtain its own connection and
    close it when finished.
    """

    os.makedirs(
        DATABASE_DIR,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10
    )

    connection.row_factory = sqlite3.Row

    # Enable foreign-key enforcement.
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    # WAL keeps readers from blocking on the writer, which matters
    # because the web layer runs synchronous routes in a thread pool
    # while an agent turn may be holding a write transaction.
    connection.execute(
        "PRAGMA journal_mode = WAL"
    )

    connection.execute(
        "PRAGMA busy_timeout = 5000"
    )

    return connection


# ============================================================
# CHECK TABLE EXISTS
# ============================================================

def table_exists(
    cursor,
    table_name
):
    """
    Return True if the specified table exists.
    """

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,)
    )

    return cursor.fetchone() is not None


# ============================================================
# GET TABLE COLUMNS
# ============================================================

def get_table_columns(
    cursor,
    table_name
):
    """
    Return all column names for a table.
    """

    if not table_exists(
        cursor,
        table_name
    ):
        return set()

    cursor.execute(
        f"PRAGMA table_info({table_name})"
    )

    return {
        row["name"]
        for row in cursor.fetchall()
    }


# ============================================================
# ENSURE COLUMN
# ============================================================

def ensure_column(
    cursor,
    table_name,
    column_name,
    column_definition
):
    """
    Add a missing column without affecting existing data.

    Returns True when a new column was added.
    """

    columns = get_table_columns(
        cursor,
        table_name
    )

    if column_name in columns:
        return False

    cursor.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_definition}
        """
    )

    return True


# ============================================================
# CREATE USERS TABLE
# ============================================================

def create_users_table(cursor):
    """
    Create the users table required for Stage 3.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL UNIQUE,

            password_hash TEXT NOT NULL,

            full_name TEXT NOT NULL,

            email TEXT UNIQUE,

            status TEXT NOT NULL DEFAULT 'active',

            role TEXT NOT NULL DEFAULT 'member',

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

        )
        """
    )


# ============================================================
# CREATE BOOKS TABLE
# ============================================================

def create_books_table(cursor):
    """
    Create the library books table.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS books (

            id INTEGER PRIMARY KEY,

            title TEXT NOT NULL,

            author TEXT NOT NULL,

            available INTEGER NOT NULL DEFAULT 1,

            category_id INTEGER NULL,

            isbn TEXT NULL,

            publisher TEXT NULL,

            pub_date TEXT NULL,

            language TEXT NULL,

            location TEXT NULL,

            description TEXT NULL,

            cover_url TEXT NULL

        )
        """
    )


# ============================================================
# CREATE CATEGORIES TABLE
# ============================================================

def create_categories_table(cursor):
    """
    Two-level category tree used for catalog classification.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            parent_id INTEGER NULL
                REFERENCES categories(id),

            name TEXT NOT NULL,

            sort_order INTEGER NOT NULL DEFAULT 0,

            is_active INTEGER NOT NULL DEFAULT 1

        )
        """
    )


# ============================================================
# CREATE BORROW RECORDS TABLE
# ============================================================

def create_borrow_records_table(cursor):
    """
    Create the borrowing records table.

    user_id is now included so every borrowing transaction
    belongs to a specific library user.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS borrow_records (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER,

            book_id INTEGER NOT NULL,

            book_title TEXT NOT NULL,

            borrowed_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            due_date TIMESTAMP NULL,

            returned_at TIMESTAMP NULL,

            fine_amount_cents INTEGER
                NOT NULL DEFAULT 0,

            fine_paid INTEGER
                NOT NULL DEFAULT 0,

            fine_paid_at TIMESTAMP NULL,

            renewals INTEGER
                NOT NULL DEFAULT 0,

            FOREIGN KEY (
                user_id
            )
            REFERENCES users(id)

        )
        """
    )


# ============================================================
# CREATE HOLDS TABLE
# ============================================================

def create_holds_table(cursor):
    """
    Create the demand queue shared by holds and purchase suggestions.

    A hold points at a book the library owns but has lent out. A
    suggestion carries no book_id: the reader asked for something the
    library does not have yet.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS holds (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            book_id INTEGER NULL,

            book_title TEXT NOT NULL,

            kind TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'waiting',

            created_at TIMESTAMP
                DEFAULT (datetime('now', 'localtime')),

            ready_at TIMESTAMP NULL,

            FOREIGN KEY (user_id)
                REFERENCES users(id),

            FOREIGN KEY (book_id)
                REFERENCES books(id)

        )
        """
    )


# ============================================================
# CREATE RETRIEVAL TABLES
# ============================================================

def create_retrieval_tables(cursor):
    """
    Create the tables used by the retrieval (RAG) layer.

    book_embeddings holds one vector per book; rag_meta records which
    embedder built the index so a change of embedder rebuilds it instead
    of comparing vectors from two different spaces.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS book_embeddings (

            book_id INTEGER PRIMARY KEY,

            embedder TEXT NOT NULL,

            vector TEXT NOT NULL,

            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (book_id)
                REFERENCES books(id)
                ON DELETE CASCADE

        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_meta (

            key TEXT PRIMARY KEY,

            value TEXT NOT NULL

        )
        """
    )


# ============================================================
# MIGRATE BORROW RECORDS
# ============================================================

def migrate_borrow_records(cursor):
    """
    Add any missing columns required by the current system.

    This allows older library.db files to be upgraded instead
    of forcing the user to delete the database.
    """

    ensure_column(
        cursor,
        "borrow_records",
        "user_id",
        "INTEGER NULL"
    )

    ensure_column(
        cursor,
        "borrow_records",
        "due_date",
        "TIMESTAMP NULL"
    )

    ensure_column(
        cursor,
        "borrow_records",
        "returned_at",
        "TIMESTAMP NULL"
    )

    ensure_column(
        cursor,
        "borrow_records",
        "fine_amount_cents",
        "INTEGER NOT NULL DEFAULT 0"
    )

    ensure_column(
        cursor,
        "borrow_records",
        "fine_paid",
        "INTEGER NOT NULL DEFAULT 0"
    )

    ensure_column(
        cursor,
        "borrow_records",
        "fine_paid_at",
        "TIMESTAMP NULL"
    )

    ensure_column(
        cursor,
        "borrow_records",
        "renewals",
        "INTEGER NOT NULL DEFAULT 0"
    )


# ============================================================
# MIGRATE CATALOG COLUMNS
# ============================================================

def migrate_catalog(cursor):
    """
    Add category & metadata columns introduced by the
    multi-category catalog feature. Idempotent and safe
    for existing library.db files.
    """

    ensure_column(
        cursor,
        "books",
        "category_id",
        "INTEGER NULL"
    )

    ensure_column(
        cursor,
        "books",
        "isbn",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "books",
        "publisher",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "books",
        "pub_date",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "books",
        "language",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "books",
        "location",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "books",
        "description",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "books",
        "cover_url",
        "TEXT NULL"
    )

    ensure_column(
        cursor,
        "users",
        "role",
        "TEXT NOT NULL DEFAULT 'member'"
    )


# ============================================================
# CREATE INDEXES
# ============================================================

def create_indexes(cursor):
    """
    Add indexes for frequently used queries.

    These become useful once multiple users are supported.
    """

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_borrow_records_user_id
        ON borrow_records(user_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_borrow_records_book_id
        ON borrow_records(book_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_borrow_records_active_loan
        ON borrow_records(
            user_id,
            returned_at
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_books_category_id
        ON books(category_id)
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        uq_books_isbn
        ON books(isbn)
        WHERE isbn IS NOT NULL
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_holds_book_status
        ON holds(book_id, status)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_holds_user_status
        ON holds(user_id, status)
        """
    )

    # Due-date reminders scan every open loan in due-date order. The
    # partial index only holds rows that can still be returned, so it
    # stays small as history grows.
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_borrow_records_open_due_date
        ON borrow_records(due_date)
        WHERE returned_at IS NULL
        """
    )


# ============================================================
# CREATE DEFAULT DEMO USER
# ============================================================

def reconcile_availability(cursor):
    """
    Make books.available agree with borrow_records.

    The flag is a cache of "no active loan". Older databases can
    contain a book that is still borrowed but marked available, so
    the cached value is repaired on every startup. A book that staff
    deliberately took off the shelf (available = 0, no loan) is left
    untouched.
    """

    cursor.execute(
        """
        UPDATE books

        SET available = 0

        WHERE available = 1
        AND id IN (
            SELECT book_id
            FROM borrow_records
            WHERE returned_at IS NULL
        )
        """
    )


def create_demo_user(cursor):
    """
    Create one demo user for development and testing.

    IMPORTANT:
    The password is only a placeholder for local development.
    It will be replaced by the actual registration/login system.
    """

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
        ("demo",)
    )

    existing_user = cursor.fetchone()

    if existing_user:

        # The demo account acts as the local administrator for
        # catalog management. Upgrade existing databases so the
        # demo login keeps working without any flow changes.
        cursor.execute(
            """
            UPDATE users
            SET role = 'admin'
            WHERE id = ?
            AND role != 'admin'
            """,
            (existing_user["id"],)
        )

        return existing_user["id"]

    # The demo account is passwordless: the hash value is never
    # used for verification, it only satisfies the NOT NULL column.
    demo_password_hash = (
        "DEMO_ACCOUNT_PLACEHOLDER"
    )

    cursor.execute(
        """
        INSERT INTO users
        (
            username,
            password_hash,
            full_name,
            email,
            status,
            role
        )
        VALUES (?, ?, ?, ?, ?, 'admin')
        """,
        (
            "demo",
            demo_password_hash,
            "Demo User",
            "demo@example.com",
            "active",
        )
    )

    return cursor.lastrowid


# ============================================================
# SEED DEMO BOOKS
# ============================================================

def seed_demo_books(cursor):
    """
    Insert the demo catalogue only when the books table is empty.

    Each entry references a real, commercially published title so the
    interface can be reviewed with a realistic, professional catalogue.
    """

    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM books
        """
    )

    row = cursor.fetchone()

    if row["count"] != 0:
        return

    # Build a lookup of "Parent / Child" -> leaf category id.
    cursor.execute(
        """
        SELECT
            child.id AS child_id,
            child.name AS child_name,
            parent.name AS parent_name
        FROM categories AS child
        JOIN categories AS parent
            ON parent.id = child.parent_id
        """
    )

    leaf_ids = {}

    for category_row in cursor.fetchall():

        key = f"{category_row['parent_name']} / {category_row['child_name']}"

        leaf_ids[key] = category_row["child_id"]

    demo_books = [
        # ----------------------------------------------------
        # Computers & IT
        # ----------------------------------------------------
        {
            "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
            "author": "Robert C. Martin",
            "category": "Computers & IT / Software Engineering",
            "year": "2008",
            "cover": "https://covers.openlibrary.org/b/id/8065615-L.jpg",
            "description": (
                "A practical guide to writing clean, maintainable code through "
                "widely adopted principles and disciplined refactoring habits."
            ),
        },
        {
            "title": "The Pragmatic Programmer",
            "author": "Andy Hunt & Dave Thomas",
            "category": "Computers & IT / Software Engineering",
            "year": "1999",
            "cover": "https://covers.openlibrary.org/b/id/10143650-L.jpg",
            "description": (
                "Timeless advice on the mindset, habits and tools that make "
                "software developers effective professionals."
            ),
        },
        {
            "title": "Python Crash Course",
            "author": "Eric Matthes",
            "category": "Computers & IT / Programming Languages",
            "year": "2019",
            "cover": "https://covers.openlibrary.org/b/id/8800209-L.jpg",
            "description": (
                "A hands-on introduction to programming in Python, built around "
                "clear explanations and practical projects."
            ),
        },
        {
            "title": "Designing Data-Intensive Applications",
            "author": "Martin Kleppmann",
            "category": "Computers & IT / Data Science & Databases",
            "year": "2017",
            "cover": "https://covers.openlibrary.org/b/id/8434671-L.jpg",
            "description": (
                "A deep look at the architecture of modern data systems, from "
                "storage engines and replication to distributed consistency."
            ),
        },
        # ----------------------------------------------------
        # Literature & Fiction
        # ----------------------------------------------------
        {
            "title": "Nineteen Eighty-Four",
            "author": "George Orwell",
            "category": "Literature & Fiction / Classics & Literary Fiction",
            "year": "1949",
            "cover": "https://covers.openlibrary.org/b/id/9267242-L.jpg",
            "description": (
                "A dystopian classic portraying a totalitarian surveillance "
                "state held together by propaganda and fear."
            ),
        },
        {
            "title": "To Kill a Mockingbird",
            "author": "Harper Lee",
            "category": "Literature & Fiction / Classics & Literary Fiction",
            "year": "1960",
            "cover": "https://covers.openlibrary.org/b/id/14351077-L.jpg",
            "description": (
                "Through the eyes of a young girl in the American South, this "
                "novel confronts racial injustice and moral growth."
            ),
        },
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "category": "Literature & Fiction / Science Fiction & Fantasy",
            "year": "1965",
            "cover": "https://covers.openlibrary.org/b/id/11481354-L.jpg",
            "description": (
                "An epic science-fiction saga on the desert planet Arrakis, "
                "where politics, religion and ecology collide."
            ),
        },
        {
            "title": "Gone Girl",
            "author": "Gillian Flynn",
            "category": "Literature & Fiction / Mystery & Thriller",
            "year": "2012",
            "cover": "https://covers.openlibrary.org/b/id/8368314-L.jpg",
            "description": (
                "A psychological thriller about a marriage that unravels after "
                "the wife disappears under suspicious circumstances."
            ),
        },
        # ----------------------------------------------------
        # Humanities & Social Sciences
        # ----------------------------------------------------
        {
            "title": "Sapiens: A Brief History of Humankind",
            "author": "Yuval Noah Harari",
            "category": "Humanities & Social Sciences / History",
            "year": "2015",
            "cover": "https://covers.openlibrary.org/b/id/15247651-L.jpg",
            "description": (
                "A sweeping history of humankind, tracing how Homo sapiens came "
                "to dominate the planet through shared stories and cooperation."
            ),
        },
        {
            "title": "Thinking, Fast and Slow",
            "author": "Daniel Kahneman",
            "category": "Humanities & Social Sciences / Psychology",
            "year": "2011",
            "cover": "https://covers.openlibrary.org/b/id/13290711-L.jpg",
            "description": (
                "A Nobel laureate's exploration of the two thinking systems "
                "that shape judgement and decision-making."
            ),
        },
        # ----------------------------------------------------
        # Economics & Business
        # ----------------------------------------------------
        {
            "title": "The Intelligent Investor",
            "author": "Benjamin Graham",
            "category": "Economics & Business / Finance & Investing",
            "year": "1949",
            "cover": "https://covers.openlibrary.org/b/id/36434-L.jpg",
            "description": (
                "A foundational text on value investing, centred on long-term "
                "discipline and the margin of safety."
            ),
        },
        {
            "title": "The Lean Startup",
            "author": "Eric Ries",
            "category": "Economics & Business / Entrepreneurship & Innovation",
            "year": "2011",
            "cover": "https://covers.openlibrary.org/b/id/7104760-L.jpg",
            "description": (
                "Introduces the build-measure-learn cycle for developing "
                "products iteratively and validating ideas quickly."
            ),
        },
        # ----------------------------------------------------
        # Natural Sciences
        # ----------------------------------------------------
        {
            "title": "A Brief History of Time",
            "author": "Stephen Hawking",
            "category": "Natural Sciences / Physics & Astronomy",
            "year": "1988",
            "cover": "https://covers.openlibrary.org/b/id/10432365-L.jpg",
            "description": (
                "An accessible account of cosmology, from the big bang and black "
                "holes to the nature of time itself."
            ),
        },
        {
            "title": "The Selfish Gene",
            "author": "Richard Dawkins",
            "category": "Natural Sciences / Biology",
            "year": "1976",
            "cover": "https://covers.openlibrary.org/b/id/133936-L.jpg",
            "description": (
                "A landmark view of evolution that frames the gene as the "
                "principal unit of natural selection."
            ),
        },
        # ----------------------------------------------------
        # Engineering & Technology
        # ----------------------------------------------------
        {
            "title": "The Art of Electronics",
            "author": "Paul Horowitz & Winfield Hill",
            "category": "Engineering & Technology / Electrical & Computer Engineering",
            "year": "2020",
            "cover": "https://covers.openlibrary.org/b/id/10527043-L.jpg",
            "description": (
                "A comprehensive, practical reference on analog and digital "
                "circuit design used by engineers and hobbyists alike."
            ),
        },
        {
            "title": "Structures: Or Why Things Don't Fall Down",
            "author": "J. E. Gordon",
            "category": "Engineering & Technology / Mechanical & Civil Engineering",
            "year": "1978",
            "cover": "https://covers.openlibrary.org/b/id/164385-L.jpg",
            "description": (
                "Explains why buildings and bridges stand up, revealing the "
                "science of structures in clear, everyday language."
            ),
        },
        # ----------------------------------------------------
        # Arts & Design
        # ----------------------------------------------------
        {
            "title": "The Design of Everyday Things",
            "author": "Donald A. Norman",
            "category": "Arts & Design / Design & UX",
            "year": "1988",
            "cover": "https://covers.openlibrary.org/b/isbn/9780465050659-L.jpg",
            "description": (
                "Explains how thoughtful design supports intuitive use through "
                "concepts such as affordances and signifiers."
            ),
        },
        {
            "title": "The Story of Art",
            "author": "E. H. Gombrich",
            "category": "Arts & Design / Art History & Visual Arts",
            "year": "1950",
            "cover": "https://covers.openlibrary.org/b/id/538390-L.jpg",
            "description": (
                "A widely loved introduction to the history of art, from "
                "prehistoric cave paintings to the modern era."
            ),
        },
        # ----------------------------------------------------
        # Health & Wellbeing
        # ----------------------------------------------------
        {
            "title": "Why We Sleep",
            "author": "Matthew Walker",
            "category": "Health & Wellbeing / Health & Medicine",
            "year": "2017",
            "cover": "https://covers.openlibrary.org/b/id/8814155-L.jpg",
            "description": (
                "Explains the science of sleep and its essential role in "
                "memory, health and daily performance."
            ),
        },
        {
            "title": "Breath: The New Science of a Lost Art",
            "author": "James Nestor",
            "category": "Health & Wellbeing / Fitness & Nutrition",
            "year": "2020",
            "cover": "https://covers.openlibrary.org/b/id/10096454-L.jpg",
            "description": (
                "Investigates how the way we breathe shapes health, drawing on "
                "medicine, anthropology and age-old practices."
            ),
        },
        # ----------------------------------------------------
        # Children & Young Adult
        # ----------------------------------------------------
        {
            "title": "Charlotte's Web",
            "author": "E. B. White",
            "category": "Children & Young Adult / Middle-Grade Fiction",
            "year": "1952",
            "cover": "https://covers.openlibrary.org/b/id/8461797-L.jpg",
            "description": (
                "A beloved children's novel about the friendship between a pig "
                "named Wilbur and a wise spider named Charlotte."
            ),
        },
        {
            "title": "The Little Prince",
            "author": "Antoine de Saint-Exupéry",
            "category": "Children & Young Adult / Middle-Grade Fiction",
            "year": "1943",
            "cover": "https://covers.openlibrary.org/b/isbn/9780156012195-L.jpg",
            "description": (
                "A poetic fable about a young prince's journeys across planets "
                "and what he learns about love, friendship and loss."
            ),
        },
        # ----------------------------------------------------
        # Education & Reference
        # ----------------------------------------------------
        {
            "title": "On Writing Well",
            "author": "William Zinsser",
            "category": "Education & Reference / Writing Guides & Reference",
            "year": "1976",
            "cover": "https://covers.openlibrary.org/b/id/20450-L.jpg",
            "description": (
                "A classic guide to writing nonfiction with clarity, simplicity "
                "and confidence."
            ),
        },
        {
            "title": "Make It Stick: The Science of Successful Learning",
            "author": "Peter C. Brown, Henry L. Roediger III & Mark A. McDaniel",
            "category": "Education & Reference / Education & Teaching",
            "year": "2014",
            "cover": "https://covers.openlibrary.org/b/id/8188891-L.jpg",
            "description": (
                "Presents evidence-based learning techniques that lead to "
                "durable, long-term understanding."
            ),
        },
        # ----------------------------------------------------
        # Second pass: fills out the leaf categories that only
        # had a heading, so browsing a category is never empty.
        # ----------------------------------------------------
        {
            "title": "Artificial Intelligence: A Modern Approach",
            "author": "Stuart Russell & Peter Norvig",
            "category": "Computers & IT / Artificial Intelligence",
            "year": "2020",
            "cover": "https://covers.openlibrary.org/b/id/13271556-L.jpg",
            "description": (
                "The standard text on intelligent agents, search, reasoning "
                "and machine learning, written for a first course in AI."
            ),
        },
        {
            "title": "Eloquent JavaScript",
            "author": "Marijn Haverbeke",
            "category": "Computers & IT / Web & Mobile Development",
            "year": "2018",
            "cover": "https://covers.openlibrary.org/b/id/7082166-L.jpg",
            "description": (
                "A modern introduction to JavaScript, the browser and Node, "
                "built around writing programs from the first page."
            ),
        },
        {
            "title": "The Web Application Hacker's Handbook",
            "author": "Dafydd Stuttard & Marcus Pinto",
            "category": "Computers & IT / Cybersecurity & Networking",
            "year": "2011",
            "cover": "https://covers.openlibrary.org/b/id/8733893-L.jpg",
            "description": (
                "How web applications are attacked and defended, with the "
                "techniques and tooling used in real penetration tests."
            ),
        },
        {
            "title": "The C Programming Language",
            "author": "Brian W. Kernighan & Dennis M. Ritchie",
            "category": "Computers & IT / Programming Languages",
            "year": "1978",
            "cover": "https://covers.openlibrary.org/b/id/6684943-L.jpg",
            "description": (
                "The concise original reference for C, written by the "
                "language's designer and its most influential teacher."
            ),
        },
        {
            "title": "Leaves of Grass",
            "author": "Walt Whitman",
            "category": "Literature & Fiction / Poetry & Drama",
            "year": "1855",
            "cover": "https://covers.openlibrary.org/b/id/9000447-L.jpg",
            "description": (
                "Whitman's lifelong book of poems, celebrating the body, the "
                "nation and the ordinary person."
            ),
        },
        {
            "title": "Normal People",
            "author": "Sally Rooney",
            "category": "Literature & Fiction / Contemporary & Romance",
            "year": "2018",
            "cover": "https://covers.openlibrary.org/b/id/8794265-L.jpg",
            "description": (
                "Two people circle each other through school and university in "
                "a close study of intimacy and class."
            ),
        },
        {
            "title": "Meditations",
            "author": "Marcus Aurelius",
            "category": "Humanities & Social Sciences / Philosophy & Ethics",
            "year": "180",
            "cover": "https://covers.openlibrary.org/b/id/211529-L.jpg",
            "description": (
                "A Roman emperor's private notes on self-discipline, duty and "
                "the Stoic view of what is worth wanting."
            ),
        },
        {
            "title": "The Origins of Totalitarianism",
            "author": "Hannah Arendt",
            "category": "Humanities & Social Sciences / Politics & Society",
            "year": "1951",
            "cover": "https://covers.openlibrary.org/b/id/10793645-L.jpg",
            "description": (
                "Arendt's study of how antisemitism, imperialism and "
                "propaganda made totalitarian rule possible."
            ),
        },
        {
            "title": "Guns, Germs, and Steel",
            "author": "Jared Diamond",
            "category": "Humanities & Social Sciences / Geography & Culture",
            "year": "1997",
            "cover": "https://covers.openlibrary.org/b/id/7884018-L.jpg",
            "description": (
                "An argument that geography and biology, not culture, "
                "explain why societies developed at different rates."
            ),
        },
        {
            "title": "Principles of Economics",
            "author": "N. Gregory Mankiw",
            "category": "Economics & Business / Economics",
            "year": "1997",
            "cover": "https://covers.openlibrary.org/b/id/19884-L.jpg",
            "description": (
                "A teaching-first introduction to supply, demand, markets and "
                "the way economists read the world."
            ),
        },
        {
            "title": "High Output Management",
            "author": "Andrew S. Grove",
            "category": "Economics & Business / Management & Leadership",
            "year": "1983",
            "cover": "https://covers.openlibrary.org/b/id/421244-L.jpg",
            "description": (
                "Intel's long-serving chief executive on running teams "
                "through measurable output rather than activity."
            ),
        },
        {
            "title": "Influence: The Psychology of Persuasion",
            "author": "Robert B. Cialdini",
            "category": "Economics & Business / Marketing & Sales",
            "year": "1984",
            "cover": "https://covers.openlibrary.org/b/id/13231578-L.jpg",
            "description": (
                "The six principles salespeople and marketers lean on, and "
                "why they work on almost everyone."
            ),
        },
        {
            "title": "Concrete Mathematics",
            "author": "Ronald L. Graham, Donald E. Knuth & Oren Patashnik",
            "category": "Natural Sciences / Mathematics",
            "year": "1989",
            "cover": "https://covers.openlibrary.org/b/id/135182-L.jpg",
            "description": (
                "The maths that computer science actually needs, taught "
                "through sums, recurrences and generating functions."
            ),
        },
        {
            "title": "Silent Spring",
            "author": "Rachel Carson",
            "category": "Natural Sciences / Chemistry & Earth Science",
            "year": "1962",
            "cover": "https://covers.openlibrary.org/b/id/3825693-L.jpg",
            "description": (
                "The book that turned pesticide pollution into a public "
                "question and helped start the environmental movement."
            ),
        },
        {
            "title": "Sustainable Energy - Without the Hot Air",
            "author": "David J. C. MacKay",
            "category": "Engineering & Technology / Energy & Environment",
            "year": "2009",
            "cover": "https://covers.openlibrary.org/b/id/7243923-L.jpg",
            "description": (
                "Energy numbers rather than slogans, worked through until the "
                "options for a low-carbon country are legible."
            ),
        },
        {
            "title": "The Architecture of Happiness",
            "author": "Alain de Botton",
            "category": "Arts & Design / Architecture",
            "year": "2006",
            "cover": "https://covers.openlibrary.org/b/id/5314605-L.jpg",
            "description": (
                "Why buildings move us, and what the shape of a room says "
                "about the life expected inside it."
            ),
        },
        {
            "title": "Understanding Comics",
            "author": "Scott McCloud",
            "category": "Arts & Design / Film, Music & Photography",
            "year": "1993",
            "cover": "https://covers.openlibrary.org/b/id/10679940-L.jpg",
            "description": (
                "A comic about comics that explains panels, time and the "
                "grammar shared by images in sequence."
            ),
        },
        {
            "title": "The Body Keeps the Score",
            "author": "Bessel van der Kolk",
            "category": "Health & Wellbeing / Mental Health & Self-Care",
            "year": "2014",
            "cover": "https://covers.openlibrary.org/b/id/8315367-L.jpg",
            "description": (
                "How trauma is held in the body, and what treatment that "
                "actually helps looks like."
            ),
        },
        {
            "title": "The Very Hungry Caterpillar",
            "author": "Eric Carle",
            "category": "Children & Young Adult / Picture Books & Early Readers",
            "year": "1969",
            "cover": "https://covers.openlibrary.org/b/id/7835968-L.jpg",
            "description": (
                "A caterpillar eats its way through the week and emerges as "
                "something else, told in cut-paper colour."
            ),
        },
        {
            "title": "The Hate U Give",
            "author": "Angie Thomas",
            "category": "Children & Young Adult / Young Adult Fiction",
            "year": "2017",
            "cover": "https://covers.openlibrary.org/b/id/11521588-L.jpg",
            "description": (
                "A teenager finds her voice after witnessing a police "
                "shooting, caught between two worlds."
            ),
        },
        {
            "title": "Fluent Forever",
            "author": "Gabriel Wyner",
            "category": "Education & Reference / Study Skills & Language Learning",
            "year": "2014",
            "cover": "https://covers.openlibrary.org/b/id/9413708-L.jpg",
            "description": (
                "A memory-and-pronunciation method for learning a language "
                "without moving abroad."
            ),
        },
    ]

    for book in demo_books:

        category_id = leaf_ids.get(book["category"])

        if category_id is None:

            raise ValueError(f"Unknown demo category: {book['category']}")

        cursor.execute(
            """
            INSERT INTO books
            (
                title,
                author,
                available,
                category_id,
                publisher,
                pub_date,
                language,
                description,
                cover_url
            )
            VALUES (?, ?, 1, ?, NULL, ?, 'English', ?, ?)
            """,
            (
                book["title"],
                book["author"],
                category_id,
                book["year"],
                book["description"],
                book["cover"],
            )
        )


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():
    """
    Create and migrate the database safely.

    Existing data is preserved.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Create base tables
        # ----------------------------------------------------

        create_users_table(
            cursor
        )

        create_books_table(
            cursor
        )

        create_borrow_records_table(
            cursor
        )

        create_categories_table(
            cursor
        )

        create_holds_table(
            cursor
        )

        create_retrieval_tables(
            cursor
        )

        # ----------------------------------------------------
        # Migrate old tables & add catalog columns
        # ----------------------------------------------------

        migrate_borrow_records(
            cursor
        )

        migrate_catalog(
            cursor
        )

        # ----------------------------------------------------
        # Indexes
        # ----------------------------------------------------

        create_indexes(
            cursor
        )

        # ----------------------------------------------------
        # Repair cached availability
        # ----------------------------------------------------

        reconcile_availability(
            cursor
        )

        # ----------------------------------------------------
        # Demo data
        # ----------------------------------------------------

        create_demo_user(
            cursor
        )

        seed_categories(
            cursor
        )

        seed_demo_books(
            cursor
        )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


def seed_categories(cursor):
    """
    Insert the default two-level category catalogue.
    Idempotent: existing rows are never duplicated.
    """

    top_level = [
        (1, "Computers & IT"),
        (2, "Literature & Fiction"),
        (3, "Humanities & Social Sciences"),
        (4, "Economics & Business"),
        (5, "Natural Sciences"),
        (6, "Engineering & Technology"),
        (7, "Arts & Design"),
        (8, "Health & Wellbeing"),
        (9, "Children & Young Adult"),
        (10, "Education & Reference"),
    ]

    children = [
        (1, "Programming Languages"),
        (1, "Web & Mobile Development"),
        (1, "Artificial Intelligence"),
        (1, "Data Science & Databases"),
        (1, "Software Engineering"),
        (1, "Cybersecurity & Networking"),
        (2, "Classics & Literary Fiction"),
        (2, "Science Fiction & Fantasy"),
        (2, "Mystery & Thriller"),
        (2, "Contemporary & Romance"),
        (2, "Poetry & Drama"),
        (3, "Philosophy & Ethics"),
        (3, "History"),
        (3, "Psychology"),
        (3, "Politics & Society"),
        (3, "Geography & Culture"),
        (4, "Economics"),
        (4, "Management & Leadership"),
        (4, "Finance & Investing"),
        (4, "Entrepreneurship & Innovation"),
        (4, "Marketing & Sales"),
        (5, "Mathematics"),
        (5, "Physics & Astronomy"),
        (5, "Biology"),
        (5, "Chemistry & Earth Science"),
        (6, "Electrical & Computer Engineering"),
        (6, "Mechanical & Civil Engineering"),
        (6, "Energy & Environment"),
        (7, "Art History & Visual Arts"),
        (7, "Design & UX"),
        (7, "Architecture"),
        (7, "Film, Music & Photography"),
        (8, "Health & Medicine"),
        (8, "Fitness & Nutrition"),
        (8, "Mental Health & Self-Care"),
        (9, "Picture Books & Early Readers"),
        (9, "Middle-Grade Fiction"),
        (9, "Young Adult Fiction"),
        (10, "Education & Teaching"),
        (10, "Study Skills & Language Learning"),
        (10, "Writing Guides & Reference"),
    ]

    rows = []

    for category_id, name in top_level:

        rows.append(
            (
                category_id,
                None,
                name,
                category_id,
                1
            )
        )

    next_id = 101

    for parent_id, name in children:

        rows.append(
            (
                next_id,
                parent_id,
                name,
                next_id,
                1
            )
        )

        next_id += 1

    cursor.executemany(
        """
        INSERT OR IGNORE INTO categories (
            id,
            parent_id,
            name,
            sort_order,
            is_active
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        rows
    )


# ============================================================
# AUTOMATIC INITIALIZATION
# ============================================================

initialize_database()
