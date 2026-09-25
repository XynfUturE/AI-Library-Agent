"""Shared fixtures for the library agent test suite.

The database path is redirected through LIBRARY_DB_PATH before any
application module is imported, so the tests never touch the real
database/library.db file.
"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:

    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


TEST_DB_DIR = tempfile.mkdtemp(
    prefix="library-agent-tests-"
)

os.environ["LIBRARY_DB_PATH"] = str(
    Path(TEST_DB_DIR) / "library.db"
)

# The agent reads the key at construction time only, so a dummy value
# keeps the tests offline without a real DeepSeek account.
os.environ.setdefault(
    "DEEPSEEK_API_KEY",
    "test-key",
)


@pytest.fixture(scope="session")
def app_database():
    """Create the throwaway database once per test session."""

    from agent import database

    database.initialize_database()

    return database.DATABASE_PATH


@pytest.fixture()
def new_user(app_database):
    """Register a fresh member so tests never share borrow state."""

    from agent.auth import register_user

    result = register_user(
        "reader_"
        +
        uuid.uuid4().hex[:8],
        "Passw0rd!23",
        "Test Reader",
    )

    assert result["success"] is True, result

    return result["user"]


@pytest.fixture()
def available_book(app_database):
    """Return one seeded book that is currently on the shelf."""

    from agent.tools import list_available_books

    books = list_available_books()

    assert books, "seed data must contain available books"

    return books[0]
