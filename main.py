"""Terminal client for the AI Library Agent.

This is a thin client: authentication comes from agent.auth and every
library operation goes through the same LibraryAgent instance the web
UI uses, so the agent loop lives in exactly one place
(agent/core.py).

Anything that is not a slash command is sent to the LLM, which can
call any of the library tools with the signed-in user's identity.
"""

import sys

from dotenv import load_dotenv

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from agent.auth import (
    authenticate_user,
    login_demo_user,
    register_user,
)

from agent.core import LibraryAgent

from agent.tools import (
    borrow_book,
    cancel_hold,
    check_book_availability,
    get_borrow_history,
    get_current_borrowed_books,
    get_my_holds,
    get_overdue_books,
    get_unpaid_fines,
    list_available_books,
    request_book,
    return_book,
    search_books,
)


console = Console()


# ============================================================
# SLASH COMMANDS
#
# Direct tool calls: no LLM round trip, no token cost. Each entry
# is (description, function, needs_user_id).
# ============================================================

SLASH_COMMANDS = {
    "available": (
        "List the books that are on the shelf",
        list_available_books,
        False,
    ),
    "loans": (
        "List your current loans",
        get_current_borrowed_books,
        True,
    ),
    "overdue": (
        "List your overdue books",
        get_overdue_books,
        True,
    ),
    "fines": (
        "List your unpaid fines",
        get_unpaid_fines,
        True,
    ),
    "history": (
        "List your borrowing history",
        get_borrow_history,
        True,
    ),
    "holds": (
        "List your holds and purchase suggestions",
        get_my_holds,
        True,
    ),
}


def print_help():

    table = Table(
        show_header=False,
        box=None,
    )

    fixed_commands = [
        (
            "/search <text>",
            "Search books by title or author",
        ),
        (
            "/borrow <id>",
            "Borrow a book",
        ),
        (
            "/return <id>",
            "Return a book",
        ),
        (
            "/check <id>",
            "Check whether a book is available",
        ),
        (
            "/request <id|title>",
            "Queue a hold, or suggest a purchase",
        ),
        (
            "/cancel <hold id>",
            "Withdraw a hold or suggestion",
        ),
    ]

    for command, description in fixed_commands:

        table.add_row(
            command,
            description,
        )

    for name, (
        description,
        _function,
        _needs_user_id,
    ) in SLASH_COMMANDS.items():

        table.add_row(
            "/" + name,
            description,
        )

    table.add_row(
        "/help",
        "Show this list",
    )

    table.add_row(
        "/quit",
        "Exit",
    )

    console.print(
        table
    )


def render_result(result):
    """Render any tool result without per-tool formatting code."""

    if isinstance(
        result,
        dict
    ):

        if result.get("success") is False:

            console.print(
                "[red]"
                + str(
                    result.get(
                        "message",
                        "The operation failed.",
                    )
                )
                + "[/red]"
            )

            return

        message = result.get("message")

        if message:

            console.print(
                str(message)
            )

        for key, value in result.items():

            if key in (
                "success",
                "message",
            ):

                continue

            if isinstance(
                value,
                dict
            ):

                for sub_key, sub_value in value.items():

                    console.print(
                        f"  {sub_key}: {sub_value}"
                    )

            elif not isinstance(
                value,
                list
            ):

                console.print(
                    f"  {key}: {value}"
                )

        return

    if isinstance(
        result,
        list
    ):

        rows = [
            row
            for row in result
            if isinstance(row, dict)
        ]

        if not rows:

            console.print(
                "No results."
            )

            return

        table = Table()

        columns = list(
            rows[0].keys()
        )

        for column in columns:

            table.add_column(
                str(column)
            )

        for row in rows:

            table.add_row(
                *[
                    str(
                        row.get(column, "")
                    )
                    for column in columns
                ]
            )

        console.print(
            table
        )

        return

    console.print(
        str(result)
    )


def run_slash_command(
    command,
    argument,
    user_id,
):
    """Run a direct tool call. Returns False when the CLI should exit."""

    if command in (
        "quit",
        "exit",
    ):

        return False

    if command == "help":

        print_help()

        return True

    if command == "search":

        if not argument:

            console.print(
                "Usage: /search <text>"
            )

            return True

        render_result(
            search_books(argument)
        )

        return True

    if command in (
        "borrow",
        "return",
        "check",
    ):

        if not argument.isdigit():

            console.print(
                f"Usage: /{command} <book id>"
            )

            return True

        book_id = int(argument)

        if command == "borrow":

            render_result(
                borrow_book(book_id, user_id)
            )

        elif command == "return":

            render_result(
                return_book(book_id, user_id)
            )

        else:

            render_result(
                check_book_availability(book_id)
            )

        return True

    if command == "request":

        if not argument:

            console.print(
                "Usage: /request <book id or title>"
            )

            return True

        if argument.isdigit():

            result = request_book(
                user_id,
                book_id=int(argument),
            )

        else:

            result = request_book(
                user_id,
                title=argument,
            )

        render_result(
            result
        )

        return True

    if command == "cancel":

        if not argument.isdigit():

            console.print(
                "Usage: /cancel <hold id>"
            )

            return True

        render_result(
            cancel_hold(
                user_id,
                int(argument),
            )
        )

        return True

    if command in SLASH_COMMANDS:

        _description, function, needs_user_id = (
            SLASH_COMMANDS[command]
        )

        if needs_user_id:

            render_result(
                function(user_id)
            )

        else:

            render_result(
                function()
            )

        return True

    console.print(
        f"Unknown command: /{command}. Type /help."
    )

    return True


# ============================================================
# AGENT CHAT
# ============================================================

def ask_agent(
    agent,
    message,
):

    console.print()

    reply = None

    try:

        for event in agent.chat_stream(message):

            event_type = event.get("type")

            if event_type == "tool_start":

                console.print(
                    "[cyan]"
                    + str(event.get("message", ""))
                    + "[/cyan]"
                )

            elif event_type == "tool_error":

                console.print(
                    "[red]"
                    + str(event.get("message", ""))
                    + "[/red]"
                )

            elif event_type == "final":

                reply = event.get(
                    "message",
                    "",
                )

            elif event_type == "error":

                console.print(
                    "[red]"
                    + str(event.get("message", ""))
                    + "[/red]"
                )

    except ValueError as error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    if reply:

        console.print(
            Panel(
                Markdown(reply),
                border_style="green",
            )
        )


def chat_loop(
    agent,
    user,
):

    console.print(
        f"\nSigned in as [bold]{user['username']}[/bold]. "
        "Type /help for commands, /quit to exit.\n"
    )

    while True:

        try:

            message = Prompt.ask(
                "[bold green]you[/bold green]"
            ).strip()

        except (
            EOFError,
            KeyboardInterrupt,
        ):

            console.print()

            return

        if not message:

            continue

        if message.startswith("/"):

            parts = message[1:].split(
                maxsplit=1
            )

            command = parts[0].strip().lower()

            argument = (
                parts[1].strip()
                if len(parts) > 1
                else ""
            )

            if not run_slash_command(
                command,
                argument,
                user["id"],
            ):

                return

            continue

        ask_agent(
            agent,
            message,
        )


# ============================================================
# AUTHENTICATION
# ============================================================

def sign_in():
    """Return the authenticated user, or None to exit."""

    while True:

        console.print(
            Panel(
                "[1] Login\n"
                "[2] Demo account\n"
                "[3] Register\n"
                "[4] Quit",
                title="Welcome",
            )
        )

        choice = Prompt.ask(
            "Choose",
            choices=[
                "1",
                "2",
                "3",
                "4",
            ],
            default="2",
        )

        if choice == "4":

            return None

        if choice == "2":

            result = login_demo_user()

        elif choice == "1":

            result = authenticate_user(
                Prompt.ask("Username"),
                Prompt.ask(
                    "Password",
                    password=True,
                ),
            )

        else:

            result = register_user(
                Prompt.ask("Username"),
                Prompt.ask(
                    "Password",
                    password=True,
                ),
                Prompt.ask("Full name"),
                Prompt.ask(
                    "Email (optional)",
                    default="",
                ) or None,
            )

        if result.get("success"):

            user = result.get(
                "user"
            )

            if user:

                return user

        console.print(
            "[red]"
            + str(result.get("message"))
            + "[/red]"
        )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    load_dotenv()

    console.print(
        Rule(
            "[bold]AI Library Agent[/bold]"
        )
    )

    user = sign_in()

    if user is None:

        return

    try:

        agent = LibraryAgent(
            user_id=user["id"]
        )

    except ValueError as error:

        console.print(
            f"[red]{error}[/red]"
        )

        console.print(
            "Set DEEPSEEK_API_KEY in .env "
            "to enable the AI assistant."
        )

        return

    chat_loop(
        agent,
        user,
    )


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        console.print()

        sys.exit(0)
