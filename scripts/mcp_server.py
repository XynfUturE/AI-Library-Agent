"""Expose the library tools to any MCP client (Codex, Claude Desktop, ...).

MCP has no session concept, so the server is bound to one library user
chosen at startup. The user id is injected here, exactly like the web
layer does for the chat: the model never supplies it.

    pip install -r requirements.txt -r requirements-mcp.txt
    python scripts/mcp_server.py --user-id 1
"""

import argparse
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from mcp.server.mcpserver import MCPServer

from agent import tools as library_tools


INSTRUCTIONS = (
    "Library assistant tools. Every call runs as the single library "
    "user this server was started for; never ask for a user id."
)


def build_server(user_id: int) -> MCPServer:
    """Build an MCP server whose tools act as `user_id`."""

    if not library_tools.user_exists(user_id):

        raise SystemExit(
            f"Unknown library user id: {user_id}"
        )

    server = MCPServer(
        name="ai-library-agent",
        instructions=INSTRUCTIONS,
        version="1.0.0",
    )

    # --------------------------------------------------------
    # Catalogue (no user identity involved)
    # --------------------------------------------------------

    @server.tool()
    def search_books(keyword: str) -> list:
        """Search books by title or author keyword."""

        return library_tools.search_books(keyword)

    @server.tool()
    def check_book_availability(book_id: int) -> dict | list:
        """Check whether a book can be borrowed right now."""

        return library_tools.check_book_availability(book_id)

    @server.tool()
    def list_available_books() -> list:
        """List the books that are currently on the shelf."""

        return library_tools.list_available_books()

    # --------------------------------------------------------
    # Loans (run as the configured user)
    # --------------------------------------------------------

    @server.tool()
    def borrow_book(book_id: int) -> dict:
        """Borrow an available book for the configured user."""

        return library_tools.borrow_book(book_id, user_id)

    @server.tool()
    def return_book(book_id: int) -> dict:
        """Return a book the configured user currently has."""

        return library_tools.return_book(book_id, user_id)

    @server.tool()
    def renew_book(book_id: int) -> dict:
        """Extend the due date of a non-overdue loan."""

        return library_tools.renew_book(book_id, user_id)

    @server.tool()
    def request_book(
        book_id: int | None = None,
        title: str | None = None,
    ) -> dict:
        """
        Ask for a book that cannot be borrowed right now.

        The library queues a hold when it owns the title, or records
        a purchase suggestion when it does not.
        """

        return library_tools.request_book(
            user_id,
            book_id,
            title,
        )

    @server.tool()
    def get_my_holds() -> list | dict:
        """List the configured user's holds and suggestions."""

        return library_tools.get_my_holds(user_id)

    @server.tool()
    def cancel_hold(hold_id: int) -> dict:
        """Withdraw one of the configured user's own requests."""

        return library_tools.cancel_hold(user_id, hold_id)

    @server.tool()
    def get_current_borrowed_books() -> list | dict:
        """List the configured user's active loans."""

        return library_tools.get_current_borrowed_books(user_id)

    @server.tool()
    def get_overdue_books() -> list | dict:
        """List the configured user's overdue loans."""

        return library_tools.get_overdue_books(user_id)

    @server.tool()
    def get_book_loan_details(book_id: int) -> dict:
        """Loan details for one book and the configured user."""

        return library_tools.get_book_loan_details(
            book_id,
            user_id,
        )

    @server.tool()
    def get_borrow_history() -> list | dict:
        """List the configured user's borrowing history."""

        return library_tools.get_borrow_history(user_id)

    # --------------------------------------------------------
    # Fines
    # --------------------------------------------------------

    @server.tool()
    def calculate_fine(book_id: int) -> dict:
        """Calculate the current or final fine for one book."""

        return library_tools.calculate_fine(
            book_id,
            user_id,
        )

    @server.tool()
    def get_unpaid_fines() -> list | dict:
        """List the configured user's unpaid fines."""

        return library_tools.get_unpaid_fines(user_id)

    @server.tool()
    def pay_fine(book_id: int) -> dict:
        """Pay an unpaid final fine."""

        return library_tools.pay_fine(
            book_id,
            user_id,
        )

    return server


def main(argv=None):

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=int(
            os.getenv(
                "LIBRARY_MCP_USER_ID",
                "0",
            )
            or
            0
        ),
        help=(
            "library user the tools act as "
            "(or set LIBRARY_MCP_USER_ID)"
        ),
    )

    args = parser.parse_args(
        argv
    )

    if args.user_id <= 0:

        parser.error(
            "--user-id is required "
            "(or set LIBRARY_MCP_USER_ID)"
        )

    build_server(
        args.user_id
    ).run()

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
