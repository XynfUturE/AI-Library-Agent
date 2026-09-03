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

DATABASE_PATH = os.path.join(
    DATABASE_DIR,
    "library.db"
)


# ============================================================
# DATABASE SETTINGS
# ============================================================

DEFAULT_LOAN_DAYS = 14

FINE_RATE_CENTS_PER_DAY = 50


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

            FOREIGN KEY (
                user_id
            )
            REFERENCES users(id)

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


# ============================================================
# CREATE DEFAULT DEMO USER
# ============================================================

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

    # Temporary placeholder hash.
    # Real authentication will be implemented in Stage 3.
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
    Insert demo books only when the books table is empty.
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
        # Demo data
        # ----------------------------------------------------

        create_demo_user(
            cursor
        )

        seed_demo_books(
            cursor
        )

        seed_categories(
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
        (1, "计算机与信息技术"),
        (2, "文学小说"),
        (3, "人文社科"),
        (4, "经济管理"),
        (5, "自然科学"),
        (6, "工程技术"),
        (7, "艺术设计"),
        (8, "教育与考试"),
        (9, "语言学习"),
        (10, "少儿读物"),
        (11, "期刊与工具书"),
        (12, "未分类"),
    ]

    children = [
        (1, "编程语言"),
        (1, "算法与数据结构"),
        (1, "人工智能"),
        (1, "数据库"),
        (1, "前端开发"),
        (1, "网络安全"),
        (1, "软件工程"),
        (1, "操作系统与运维"),
        (2, "中国文学"),
        (2, "外国文学"),
        (2, "科幻奇幻"),
        (2, "悬疑推理"),
        (2, "诗词散文"),
        (3, "哲学心理"),
        (3, "历史地理"),
        (3, "政治法律"),
        (3, "社会文化"),
        (4, "经济学"),
        (4, "市场营销"),
        (4, "人力资源"),
        (4, "财务会计"),
        (4, "自我管理"),
        (5, "数学物理"),
        (5, "生物医学"),
        (5, "天文地理"),
        (6, "机械电子"),
        (6, "建筑土木"),
        (6, "能源环境"),
        (7, "平面设计"),
        (7, "绘画书法"),
        (7, "影视音乐"),
        (8, "考研公考"),
        (8, "职业技能"),
        (8, "教育理论"),
        (9, "英语学习"),
        (9, "多语种学习"),
        (10, "绘本童话"),
        (10, "少儿科普"),
        (11, "期刊杂志"),
        (11, "工具书"),
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
# RESET DEMO DATABASE DATA
# ============================================================

def reset_demo_database():
    """
    Reset development/demo borrowing data.

    This does NOT delete users or book definitions.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Remove borrowing records
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM borrow_records
            """
        )

        # ----------------------------------------------------
        # Reset book availability
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE books
            SET available = 1
            """
        )

        # Object-Oriented Design is unavailable by default.
        cursor.execute(
            """
            UPDATE books
            SET available = 0
            WHERE id = 2
            """
        )

        # ----------------------------------------------------
        # Reset AUTOINCREMENT
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name = 'borrow_records'
            """
        )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# RESET EVERYTHING
# ============================================================

def reset_all_demo_data():
    """
    Completely reset demo users, borrowing records and
    book availability.

    This is intended for development/testing only.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Delete borrow records first because they reference
        # users.
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM borrow_records
            """
        )

        # ----------------------------------------------------
        # Delete users
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM users
            """
        )

        # ----------------------------------------------------
        # Reset books
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE books
            SET available = 1
            """
        )

        cursor.execute(
            """
            UPDATE books
            SET available = 0
            WHERE id = 2
            """
        )

        # ----------------------------------------------------
        # Reset sequences
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name IN (
                'users',
                'borrow_records'
            )
            """
        )

        # ----------------------------------------------------
        # Recreate demo user
        # ----------------------------------------------------

        create_demo_user(
            cursor
        )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# DATABASE PATH
# ============================================================

def get_database_path():
    """
    Return the absolute database path.
    """

    return DATABASE_PATH


# ============================================================
# DATABASE INFORMATION
# ============================================================

def get_database_info():
    """
    Return basic database information useful for debugging
    and development.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM users
            """
        )

        user_count = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM books
            """
        )

        book_count = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM borrow_records
            """
        )

        borrow_record_count = (
            cursor.fetchone()["count"]
        )

        return {
            "database_path":
                DATABASE_PATH,

            "users":
                user_count,

            "books":
                book_count,

            "borrow_records":
                borrow_record_count
        }

    finally:

        connection.close()


# ============================================================
# AUTOMATIC INITIALIZATION
# ============================================================

initialize_database()