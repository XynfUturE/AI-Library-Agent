import sqlite3

connection = sqlite3.connect(
    "database/library.db"
)

cursor = connection.cursor()

cursor.execute(
    """
    UPDATE borrow_records
    SET due_date = ?
    WHERE book_id = ?
    AND returned_at IS NULL
    """,
    (
        "2026-08-20 00:00:00",
        1
    )
)

connection.commit()
connection.close()

print("Overdue test prepared.")