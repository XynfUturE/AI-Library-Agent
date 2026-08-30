import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from agent.auth import (
    authenticate_user,
    login_demo_user,
    register_user,
)

from agent.errors import get_user_error_message

from agent.state import AgentState

from agent.tools import (
    search_books,
    check_book_availability,
    borrow_book,
    return_book,
    get_current_borrowed_books,
    get_overdue_books,
    get_book_loan_details,
    calculate_fine,
    get_unpaid_fines,
    pay_fine,
    get_borrow_history,
    list_available_books,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEBUG_MODE = False

MAX_STEPS = 8

MAX_CONVERSATION_USER_TURNS = 10


# ============================================================
# CONSOLE
# ============================================================

console = Console()


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError(
        "DEEPSEEK_API_KEY is not loaded. "
        "Please check your .env file."
    )


# ============================================================
# AI CLIENT
# ============================================================

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
    timeout=60.0,
)


# ============================================================
# AGENT STATE
# ============================================================

state = AgentState()


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an intelligent AI library assistant.

You help the currently authenticated library user with:

- searching for books
- checking book availability
- borrowing books
- returning books
- checking current borrowed books
- checking overdue books
- checking due dates
- calculating fines
- checking unpaid fines
- paying fines
- viewing borrowing history
- viewing available books
- recommending books


==================================================
GENERAL RULES
==================================================

Always use actual library tool results.

Never invent:

- books
- authors
- book IDs
- availability
- due dates
- fine amounts
- payment results
- borrowing results

Never claim success unless the corresponding tool
returned success=true.

Never ask the user for a user ID.

The application automatically supplies the authenticated
user ID to user-specific tools.


==================================================
NATURAL LANGUAGE UNDERSTANDING
==================================================

Understand informal, shortened and conversational wording.

Examples:

Borrowing:
- Borrow Python Programming
- I want Python Programming
- Can I borrow Python Programming?
- I'd like to check out Python Programming

Returning:
- Return Python Programming
- Return book 1
- I've finished with Python Programming

Current loans:
- What do I have?
- What books do I currently have?
- Show my current loans
- Which books haven't I returned?

Overdue:
- Am I late?
- Am I overdue?
- Do I have anything overdue?
- Which books are late?

Fines:
- Do I owe anything?
- Do I have any unpaid fines?
- How much do I owe?
- Do I have any late fees?

History:
- Show my borrowing history
- What have I borrowed before?
- Show my past loans

Recommendation:
- Recommend a book
- Recommend a programming book
- What programming books are available?
- I want something about databases
- What should I read?


==================================================
BORROWING DECISION RULES
==================================================

When the user provides a book title:

1. Use search_books first.
2. Identify the correct actual book.
3. Obtain the actual book ID.
4. Check availability.
5. Borrow only if available.

When the user explicitly provides a book ID:

1. Check availability using that ID.
2. Borrow only if available.

Never invent book IDs.

Never borrow an unavailable book.

Never call borrow_book before availability has been
verified.

After successful borrowing, stop using tools.


==================================================
AGENT PLANNING
==================================================

Use the minimum number of tool calls necessary.

For title-based borrowing:

search_books
-> check_book_availability
-> borrow_book

For an unavailable book:

search_books
-> check_book_availability
-> ask whether the user wants an alternative

For an alternative:

list_available_books
-> choose an actual available book
-> borrow_book

Do not repeatedly call the same tool with identical
arguments.

Do not call tools randomly.

Reuse reliable information already obtained during
the current task when appropriate.


==================================================
RETURNING
==================================================

For a return request:

Identify the book
-> return_book

Do not perform an unnecessary availability check.

The return tool verifies that the authenticated user
currently owns the active loan.


==================================================
CURRENT LOANS
==================================================

For current borrowed books:

Use get_current_borrowed_books.


==================================================
OVERDUE
==================================================

For general overdue questions:

Use get_overdue_books.

For a specific book:

Use get_book_loan_details.


==================================================
FINES
==================================================

For general unpaid fines:

Use get_unpaid_fines.

For a specific book:

Use calculate_fine or get_book_loan_details.


==================================================
PAYMENT
==================================================

A fine can only be paid after the related book has been
returned and a final fine has been recorded.

Never pay an estimated active-loan fine.

Never pay another user's fine.

Never pay an already paid fine.

Only report success when pay_fine returns success=true.


==================================================
BORROWING HISTORY
==================================================

Use get_borrow_history.

The application renders borrowing history using its
own Rich table.

Do NOT generate a Markdown table for borrowing history.


==================================================
BOOK RECOMMENDATION
==================================================

A recommendation does NOT automatically mean that the
user wants to borrow the book.

For a recommendation:

1. Understand the user's requirements.
2. Use list_available_books.
3. Only recommend books returned by the tool.
4. Never invent book information.
5. Rank actual available books according to the request.
6. Give a short reason for the recommendation.
7. Recommend the strongest matching available book first.
8. Never call borrow_book merely because a book was
   recommended.


==================================================
CONTEXT
==================================================

Understand references such as:

- it
- this book
- that book
- that one
- the recommended one
- your recommendation
- another one

Use context when the reference is unambiguous.

Ask for clarification when multiple books could match.


==================================================
ERROR HANDLING
==================================================

When a tool returns an error:

- explain the problem briefly
- do not claim success
- do not expose SQL
- do not expose stack traces
- do not expose implementation details

Do not repeatedly call a failed tool with identical
arguments without a genuine reason.


==================================================
IMPORTANT
==================================================

Never reveal private chain-of-thought.

Only provide short user-facing descriptions of actions.
"""


# ============================================================
# CONVERSATION HISTORY
# ============================================================

messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
]


# ============================================================
# TOOL DEFINITIONS
# ============================================================

TOOL_DEFINITIONS = [

    {
        "type": "function",
        "function": {
            "name": "search_books",
            "description": (
                "Search books by title keyword."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Book title keyword.",
                    }
                },
                "required": ["keyword"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "check_book_availability",
            "description": (
                "Check whether a specific book is currently "
                "available for borrowing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID.",
                    }
                },
                "required": ["book_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "borrow_book",
            "description": (
                "Borrow an available book for the "
                "authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID.",
                    }
                },
                "required": ["book_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "return_book",
            "description": (
                "Return a book currently borrowed "
                "by the authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID.",
                    }
                },
                "required": ["book_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_current_borrowed_books",
            "description": (
                "Get all books currently borrowed "
                "by the authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_overdue_books",
            "description": (
                "Get all currently overdue books "
                "belonging to the authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_book_loan_details",
            "description": (
                "Get active or most recent loan details "
                "for a specific book belonging to the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID.",
                    }
                },
                "required": ["book_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "calculate_fine",
            "description": (
                "Calculate the current or final fine "
                "for a specific book belonging to the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID.",
                    }
                },
                "required": ["book_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_unpaid_fines",
            "description": (
                "Get unpaid final fines belonging "
                "to the authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "pay_fine",
            "description": (
                "Pay an unpaid final fine for a returned book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID.",
                    }
                },
                "required": ["book_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "get_borrow_history",
            "description": (
                "Get the authenticated user's "
                "borrowing history."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "list_available_books",
            "description": (
                "List all books currently available for "
                "borrowing. Use this for available-book "
                "queries, alternatives and recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ============================================================
# BASIC HELPERS
# ============================================================

def debug_print(*args, **kwargs):

    if DEBUG_MODE:
        console.print(*args, **kwargs)


def safe_float(value, default=0.0):

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def short_date(value):

    if not value:
        return "-"

    return str(value)[:10]


def require_login():

    if state.is_logged_in():
        return True

    show_error(
        "Please log in before using this feature."
    )

    return False


# ============================================================
# UI HELPERS
# ============================================================

def show_info(message):

    console.print()

    console.print(
        Panel(
            str(message),
            title="ℹ INFORMATION",
            border_style="yellow",
            padding=(1, 2),
        )
    )


def show_success(message):

    console.print()

    console.print(
        Panel(
            str(message),
            title="✓ SUCCESS",
            border_style="green",
            padding=(1, 2),
        )
    )


def show_error(message):

    console.print()

    console.print(
        Panel(
            str(message),
            title="⚠ ERROR",
            border_style="red",
            padding=(1, 2),
        )
    )


def show_agent_action(message):

    console.print(
        f"[bright_cyan]🤖 Agent:[/bright_cyan] {message}"
    )


def show_tool_error(result):

    if not isinstance(result, dict):

        show_error(
            "The library operation could not be completed."
        )

        return

    show_error(
        result.get(
            "message",
            "The library operation could not be completed.",
        )
    )

    if DEBUG_MODE:

        debug_print(
            "[DEBUG] Error type:",
            result.get("error_type"),
        )

        debug_print(
            "[DEBUG] Internal error:",
            result.get("_debug_error"),
        )


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def reset_conversation():

    global messages

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]


def add_assistant_history(content):

    if not content:
        return

    messages.append(
        {
            "role": "assistant",
            "content": str(content),
        }
    )


def trim_messages():

    global messages

    if len(messages) <= 1:
        return

    user_indexes = [
        index
        for index, message in enumerate(messages)
        if message.get("role") == "user"
    ]

    if len(user_indexes) <= MAX_CONVERSATION_USER_TURNS:
        return

    first_kept_index = user_indexes[
        -MAX_CONVERSATION_USER_TURNS
    ]

    messages = (
        [messages[0]]
        + messages[first_kept_index:]
    )


def build_assistant_message(message):

    result = {
        "role": "assistant",
        "content": message.content or "",
    }

    if message.tool_calls:

        result["tool_calls"] = [

            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }

            for tool_call in message.tool_calls

        ]

    return result


# ============================================================
# YES / NO
# ============================================================

def is_yes_response(text):

    return text.lower().strip() in {

        "yes",
        "yes please",
        "sure",
        "okay",
        "ok",
        "y",
        "find one",
        "find another",
        "find an alternative",
        "alternative",
        "another book",
        "please find one",
    }


def is_no_response(text):

    return text.lower().strip() in {

        "no",
        "no thanks",
        "no thank you",
        "n",
        "cancel",
        "stop",
    }


# ============================================================
# ALTERNATIVE SELECTION
# ============================================================

def select_alternative(
    books,
    requested_book_id,
):

    if not isinstance(
        books,
        list,
    ):
        return None

    candidates = []

    for book in books:

        if not isinstance(
            book,
            dict,
        ):
            continue

        if book.get("id") == requested_book_id:
            continue

        candidates.append(book)

    if not candidates:
        return None

    preferred_keywords = [

        "programming",
        "database",
        "software",
        "algorithm",
        "computer",
        "python",
        "java",
        "object",
    ]

    for book in candidates:

        title = str(
            book.get(
                "title",
                "",
            )
        ).lower()

        if any(
            keyword in title
            for keyword in preferred_keywords
        ):
            return book

    return candidates[0]


# ============================================================
# ACTION MESSAGES
# ============================================================

def get_action_message(function_name):

    actions = {

        "search_books":
            "Searching for the book...",

        "check_book_availability":
            "Checking book availability...",

        "borrow_book":
            "Processing the borrowing request...",

        "return_book":
            "Processing the return request...",

        "get_current_borrowed_books":
            "Checking your current borrowed books...",

        "get_overdue_books":
            "Checking for overdue books...",

        "get_book_loan_details":
            "Checking the loan details...",

        "calculate_fine":
            "Calculating the fine...",

        "get_unpaid_fines":
            "Checking your unpaid fines...",

        "pay_fine":
            "Processing your fine payment...",

        "get_borrow_history":
            "Loading your borrowing history...",

        "list_available_books":
            "Looking for available books...",
    }

    return actions.get(
        function_name
    )


# ============================================================
# EXECUTE TOOL
# ============================================================

def execute_tool(
    function_name,
    arguments,
):

    user_id = state.current_user_id

    debug_print(
        "[DEBUG] Tool:",
        function_name,
    )

    debug_print(
        "[DEBUG] Arguments:",
        arguments,
    )

    debug_print(
        "[DEBUG] User ID:",
        user_id,
    )

    try:

        if function_name == "search_books":

            return search_books(
                arguments["keyword"]
            )

        if function_name == "check_book_availability":

            return check_book_availability(
                arguments["book_id"]
            )

        if function_name == "borrow_book":

            return borrow_book(
                arguments["book_id"],
                user_id,
            )

        if function_name == "return_book":

            return return_book(
                arguments["book_id"],
                user_id,
            )

        if function_name == "get_current_borrowed_books":

            return get_current_borrowed_books(
                user_id
            )

        if function_name == "get_overdue_books":

            return get_overdue_books(
                user_id
            )

        if function_name == "get_book_loan_details":

            return get_book_loan_details(
                arguments["book_id"],
                user_id,
            )

        if function_name == "calculate_fine":

            return calculate_fine(
                arguments["book_id"],
                user_id,
            )

        if function_name == "get_unpaid_fines":

            return get_unpaid_fines(
                user_id
            )

        if function_name == "pay_fine":

            return pay_fine(
                arguments["book_id"],
                user_id,
            )

        if function_name == "get_borrow_history":

            return get_borrow_history(
                user_id
            )

        if function_name == "list_available_books":

            return list_available_books()

        return {

            "success":
                False,

            "error_type":
                "ToolError",

            "message":
                f"Unknown tool: {function_name}",
        }

    except KeyError as error:

        debug_print(
            "[DEBUG] Missing tool argument:",
            repr(error),
        )

        return {

            "success":
                False,

            "error_type":
                "ValidationError",

            "message":
                "The AI provided incomplete information "
                "for this operation.",

            "_debug_error":
                repr(error),
        }

    except Exception as error:

        debug_print(
            "[DEBUG] Tool execution error:",
            repr(error),
        )

        return {

            "success":
                False,

            "error_type":
                "ToolError",

            "message":
                "The library operation could not be completed.",

            "_debug_error":
                repr(error),
        }


# ============================================================
# BORROW RESULT
# ============================================================

def show_borrow_result(
    current_state,
    result,
):

    if not isinstance(
        result,
        dict,
    ):

        show_error(
            "Invalid borrowing result."
        )

        return

    book = result.get(
        "book",
        {},
    )

    if not isinstance(
        book,
        dict,
    ):

        book = {}

    table = Table(
        show_header=False,
        border_style="green",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Field",
        ratio=1,
        style="bold cyan",
    )

    table.add_column(
        "Value",
        ratio=3,
        overflow="fold",
    )

    if current_state.alternative_book:

        table.add_row(
            "Requested",
            str(
                current_state.requested_book
            ),
        )

        table.add_row(
            "Requested Status",
            "[red]Unavailable[/red]",
        )

        table.add_row(
            "Alternative",
            str(
                book.get(
                    "title",
                    "Unknown",
                )
            ),
        )

    else:

        table.add_row(
            "Book",
            str(
                book.get(
                    "title",
                    "Unknown",
                )
            ),
        )

    table.add_row(
        "Author",
        str(
            book.get(
                "author",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Borrowed At",
        str(
            result.get(
                "borrowed_at",
                "-",
            )
        ),
    )

    table.add_row(
        "Due Date",
        str(
            result.get(
                "due_date",
                "-",
            )
        ),
    )

    table.add_row(
        "Status",
        "[green]✓ Borrowed successfully[/green]",
    )

    console.print()

    console.print(
        Panel(
            table,
            title="📚 BORROWING RESULT",
            border_style="green",
            padding=(1, 1),
        )
    )


# ============================================================
# RETURN RESULT
# ============================================================

def show_return_result(
    result,
):

    if not isinstance(
        result,
        dict,
    ):

        show_error(
            "Invalid return result."
        )

        return

    book = result.get(
        "book",
        {},
    )

    if not isinstance(
        book,
        dict,
    ):

        book = {}

    table = Table(
        show_header=False,
        border_style="green",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Field",
        ratio=1,
        style="bold cyan",
    )

    table.add_column(
        "Value",
        ratio=3,
        overflow="fold",
    )

    table.add_row(
        "Book",
        str(
            book.get(
                "title",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Author",
        str(
            book.get(
                "author",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Due Date",
        str(
            result.get(
                "due_date",
                "-",
            )
        ),
    )

    table.add_row(
        "Returned At",
        str(
            result.get(
                "returned_at",
                "-",
            )
        ),
    )

    if result.get(
        "is_overdue",
        False,
    ):

        table.add_row(
            "Loan Status",
            "[yellow]Returned late[/yellow]",
        )

        table.add_row(
            "Late Days",
            str(
                result.get(
                    "late_days",
                    0,
                )
            ),
        )

    else:

        table.add_row(
            "Loan Status",
            "[green]Returned on time[/green]",
        )

    fine_amount = safe_float(
        result.get(
            "fine_amount",
            0.0,
        )
    )

    table.add_row(
        "Fine",
        f"${fine_amount:.2f}",
    )

    table.add_row(
        "Fine Status",
        (
            "[yellow]Unpaid[/yellow]"
            if fine_amount > 0
            else
            "[green]No Fine[/green]"
        ),
    )

    table.add_row(
        "Status",
        "[green]✓ Returned successfully[/green]",
    )

    console.print()

    console.print(
        Panel(
            table,
            title="↩ RETURN RESULT",
            border_style="green",
            padding=(1, 1),
        )
    )


# ============================================================
# PAYMENT RESULT
# ============================================================

def show_payment_result(
    result,
):

    if not isinstance(
        result,
        dict,
    ):

        show_error(
            "Invalid payment result."
        )

        return

    if result.get(
        "success"
    ) is not True:

        show_tool_error(
            result
        )

        return

    book = result.get(
        "book",
        {},
    )

    if not isinstance(
        book,
        dict,
    ):

        book = {}

    amount = safe_float(
        result.get(
            "payment_amount",
            result.get(
                "fine_amount",
                0.0,
            ),
        )
    )

    table = Table(
        show_header=False,
        border_style="green",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Field",
        ratio=1,
        style="bold cyan",
    )

    table.add_column(
        "Value",
        ratio=3,
        overflow="fold",
    )

    table.add_row(
        "Book",
        str(
            book.get(
                "title",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Author",
        str(
            book.get(
                "author",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Payment",
        f"${amount:.2f}",
    )

    table.add_row(
        "Payment Time",
        str(
            result.get(
                "fine_paid_at",
                "-",
            )
        ),
    )

    table.add_row(
        "Status",
        "[green]✓ Paid successfully[/green]",
    )

    console.print()

    console.print(
        Panel(
            table,
            title="💳 PAYMENT RESULT",
            border_style="green",
            padding=(1, 1),
        )
    )


# ============================================================
# CURRENT BORROWED BOOKS
# ============================================================

def show_current_borrowed_books_result(
    result,
):

    if not isinstance(
        result,
        list,
    ):

        show_tool_error(
            result
        )

        return

    if not result:

        show_info(
            "You currently have no borrowed books."
        )

        return

    width = console.size.width

    if width < 100:

        table = Table(
            title="Current Borrowed Books",
            border_style="bright_cyan",
            expand=True,
            padding=(0, 1),
        )

        table.add_column(
            "Book",
            ratio=4,
            overflow="fold",
        )

        table.add_column(
            "Due",
            ratio=2,
        )

        table.add_column(
            "Status",
            ratio=2,
        )

        table.add_column(
            "Fine",
            ratio=1,
            justify="right",
        )

        for book in result:

            fine = safe_float(
                book.get(
                    "estimated_fine_amount",
                    0.0,
                )
            )

            table.add_row(

                str(
                    book.get(
                        "book_title",
                        "Unknown",
                    )
                ),

                short_date(
                    book.get(
                        "due_date"
                    )
                ),

                (
                    "[red]Overdue[/red]"
                    if book.get(
                        "is_overdue",
                        False,
                    )
                    else
                    "[green]Active[/green]"
                ),

                f"${fine:.2f}",
            )

        console.print(table)

        return

    table = Table(
        title="Current Borrowed Books",
        border_style="bright_cyan",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Book",
        ratio=4,
        overflow="fold",
    )

    table.add_column(
        "Author",
        ratio=3,
        overflow="fold",
    )

    table.add_column(
        "Borrowed",
        ratio=2,
    )

    table.add_column(
        "Due",
        ratio=2,
    )

    table.add_column(
        "Status",
        ratio=2,
    )

    table.add_column(
        "Estimated Fine",
        ratio=2,
        justify="right",
    )

    for book in result:

        fine = safe_float(
            book.get(
                "estimated_fine_amount",
                0.0,
            )
        )

        table.add_row(

            str(
                book.get(
                    "book_title",
                    "Unknown",
                )
            ),

            str(
                book.get(
                    "author",
                    "Unknown",
                )
            ),

            short_date(
                book.get(
                    "borrowed_at"
                )
            ),

            short_date(
                book.get(
                    "due_date"
                )
            ),

            (
                "[red]Overdue[/red]"
                if book.get(
                    "is_overdue",
                    False,
                )
                else
                "[green]Active[/green]"
            ),

            f"${fine:.2f}",
        )

    console.print(table)


# ============================================================
# OVERDUE BOOKS
# ============================================================

def show_overdue_books_result(
    result,
):

    if not isinstance(
        result,
        list,
    ):

        show_tool_error(
            result
        )

        return

    if not result:

        show_success(
            "You currently have no overdue books."
        )

        return

    width = console.size.width

    if width < 100:

        table = Table(
            title="Overdue Books",
            border_style="red",
            expand=True,
            padding=(0, 1),
        )

        table.add_column(
            "Book",
            ratio=4,
            overflow="fold",
        )

        table.add_column(
            "Due",
            ratio=2,
        )

        table.add_column(
            "Late",
            ratio=1,
            justify="center",
        )

        table.add_column(
            "Fine",
            ratio=1,
            justify="right",
        )

        for book in result:

            fine = safe_float(
                book.get(
                    "estimated_fine_amount",
                    0.0,
                )
            )

            table.add_row(

                str(
                    book.get(
                        "book_title",
                        "Unknown",
                    )
                ),

                short_date(
                    book.get(
                        "due_date"
                    )
                ),

                str(
                    book.get(
                        "late_days",
                        0,
                    )
                ),

                f"${fine:.2f}",
            )

        console.print(table)

        return

    table = Table(
        title="Overdue Books",
        border_style="red",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Book",
        ratio=4,
        overflow="fold",
    )

    table.add_column(
        "Author",
        ratio=3,
        overflow="fold",
    )

    table.add_column(
        "Due Date",
        ratio=2,
    )

    table.add_column(
        "Late Days",
        ratio=1,
        justify="center",
    )

    table.add_column(
        "Estimated Fine",
        ratio=2,
        justify="right",
    )

    for book in result:

        fine = safe_float(
            book.get(
                "estimated_fine_amount",
                0.0,
            )
        )

        table.add_row(

            str(
                book.get(
                    "book_title",
                    "Unknown",
                )
            ),

            str(
                book.get(
                    "author",
                    "Unknown",
                )
            ),

            short_date(
                book.get(
                    "due_date"
                )
            ),

            str(
                book.get(
                    "late_days",
                    0,
                )
            ),

            f"${fine:.2f}",
        )

    console.print(table)


# ============================================================
# FINE RESULT
# ============================================================

def show_fine_result(
    result,
):

    if not isinstance(
        result,
        dict,
    ):

        show_error(
            "Invalid fine information."
        )

        return

    if result.get(
        "success"
    ) is False:

        show_tool_error(
            result
        )

        return

    amount = safe_float(
        result.get(
            "fine_amount",
            0.0,
        )
    )

    table = Table(
        show_header=False,
        border_style="bright_cyan",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Field",
        ratio=1,
        style="bold cyan",
    )

    table.add_column(
        "Value",
        ratio=3,
        overflow="fold",
    )

    table.add_row(
        "Book",
        str(
            result.get(
                "book_title",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Loan Status",
        str(
            result.get(
                "loan_status",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Due Date",
        str(
            result.get(
                "due_date",
                "-",
            )
        ),
    )

    if result.get(
        "returned_at"
    ):

        table.add_row(
            "Returned At",
            str(
                result.get(
                    "returned_at"
                )
            ),
        )

    table.add_row(
        "Late Days",
        str(
            result.get(
                "late_days",
                0,
            )
        ),
    )

    table.add_row(
        "Overdue",
        (
            "[red]Yes[/red]"
            if result.get(
                "is_overdue",
                False,
            )
            else
            "[green]No[/green]"
        ),
    )

    table.add_row(
        "Fine",
        f"${amount:.2f}",
    )

    status = result.get(
        "fine_status",
        "Unknown",
    )

    display_status = {

        "Paid":
            "[green]Paid[/green]",

        "Unpaid":
            "[yellow]Unpaid[/yellow]",

        "Estimated":
            "[cyan]Estimated[/cyan]",

        "No Fine":
            "[green]No Fine[/green]",
    }.get(
        status,
        f"[cyan]{status}[/cyan]",
    )

    table.add_row(
        "Fine Status",
        display_status,
    )

    console.print()

    console.print(
        Panel(
            table,
            title="💰 FINE INFORMATION",
            border_style="bright_cyan",
            padding=(1, 1),
        )
    )


# ============================================================
# UNPAID FINES
# ============================================================

def show_unpaid_fines_result(
    result,
):

    if not isinstance(
        result,
        dict,
    ):

        show_error(
            "Unable to retrieve unpaid fines."
        )

        return

    if result.get(
        "success"
    ) is False:

        show_tool_error(
            result
        )

        return

    fines = result.get(
        "fines",
        [],
    )

    total = safe_float(
        result.get(
            "total_fine",
            0.0,
        )
    )

    if not fines:

        show_success(
            "You currently have no unpaid fines."
        )

        return

    width = console.size.width

    columns = [

        {
            "header": "Book",
            "ratio": 4,
            "overflow": "fold",
        }
    ]

    if width >= 100:

        columns.append(
            {
                "header": "Author",
                "ratio": 3,
                "overflow": "fold",
            }
        )

    columns.extend(
        [
            {
                "header": "Fine",
                "ratio": 1,
                "justify": "right",
            },
            {
                "header": "Status",
                "ratio": 2,
            },
        ]
    )

    table = Table(
        title="Unpaid Fines",
        border_style="yellow",
        expand=True,
        padding=(0, 1),
    )

    for column in columns:

        table.add_column(
            **column
        )

    for fine in fines:

        amount = safe_float(
            fine.get(
                "fine_amount",
                0.0,
            )
        )

        row = [

            str(
                fine.get(
                    "book_title",
                    "Unknown",
                )
            )
        ]

        if width >= 100:

            row.append(

                str(
                    fine.get(
                        "author",
                        "Unknown",
                    )
                )
            )

        row.extend(
            [
                f"${amount:.2f}",
                "[yellow]Unpaid[/yellow]",
            ]
        )

        table.add_row(
            *row
        )

    console.print(table)

    console.print()

    console.print(
        Panel(
            (
                "[bold]Total outstanding: "
                f"[yellow]${total:.2f}"
                "[/yellow][/bold]"
            ),
            border_style="yellow",
            padding=(1, 2),
        )
    )


# ============================================================
# BORROWING HISTORY
# ============================================================

def show_borrow_history_result(
    result,
):

    if not isinstance(
        result,
        list,
    ):

        show_tool_error(
            result
        )

        return

    if not result:

        show_info(
            "You currently have no borrowing records."
        )

        return

    width = console.size.width

    # --------------------------------------------------------
    # Narrow terminal
    # --------------------------------------------------------

    if width < 100:

        table = Table(
            title="Your Borrowing History",
            border_style="bright_cyan",
            expand=True,
            padding=(0, 1),
        )

        table.add_column(
            "Book",
            ratio=4,
            overflow="fold",
        )

        table.add_column(
            "Due",
            ratio=2,
        )

        table.add_column(
            "Returned",
            ratio=2,
        )

        table.add_column(
            "Fine",
            ratio=1,
            justify="right",
        )

        table.add_column(
            "Status",
            ratio=2,
        )

        for record in result:

            fine = safe_float(
                record.get(
                    "fine_amount",
                    0.0,
                )
            )

            if fine <= 0:

                status = "[green]No Fine[/green]"

            elif record.get(
                "fine_paid"
            ):

                status = "[green]Paid[/green]"

            else:

                status = "[yellow]Unpaid[/yellow]"

            returned = (

                short_date(
                    record.get(
                        "returned_at"
                    )
                )

                if record.get(
                    "returned_at"
                )

                else

                "Not returned"
            )

            table.add_row(

                str(
                    record.get(
                        "book_title",
                        "Unknown",
                    )
                ),

                short_date(
                    record.get(
                        "due_date"
                    )
                ),

                returned,

                f"${fine:.2f}",

                status,
            )

        console.print(table)

        return

    # --------------------------------------------------------
    # Medium terminal
    # --------------------------------------------------------

    if width < 130:

        table = Table(
            title="Your Borrowing History",
            border_style="bright_cyan",
            expand=True,
            padding=(0, 1),
        )

        table.add_column(
            "Book",
            ratio=4,
            overflow="fold",
        )

        table.add_column(
            "Author",
            ratio=3,
            overflow="fold",
        )

        table.add_column(
            "Borrowed",
            ratio=2,
        )

        table.add_column(
            "Due",
            ratio=2,
        )

        table.add_column(
            "Returned",
            ratio=2,
        )

        table.add_column(
            "Fine",
            ratio=1,
            justify="right",
        )

        table.add_column(
            "Status",
            ratio=2,
        )

        for record in result:

            fine = safe_float(
                record.get(
                    "fine_amount",
                    0.0,
                )
            )

            if fine <= 0:

                status = "[green]No Fine[/green]"

            elif record.get(
                "fine_paid"
            ):

                status = "[green]Paid[/green]"

            else:

                status = "[yellow]Unpaid[/yellow]"

            returned = (

                short_date(
                    record.get(
                        "returned_at"
                    )
                )

                if record.get(
                    "returned_at"
                )

                else

                "Not returned"
            )

            table.add_row(

                str(
                    record.get(
                        "book_title",
                        "Unknown",
                    )
                ),

                str(
                    record.get(
                        "author",
                        "Unknown",
                    )
                ),

                short_date(
                    record.get(
                        "borrowed_at"
                    )
                ),

                short_date(
                    record.get(
                        "due_date"
                    )
                ),

                returned,

                f"${fine:.2f}",

                status,
            )

        console.print(table)

        return

    # --------------------------------------------------------
    # Wide terminal
    # --------------------------------------------------------

    table = Table(
        title="Your Borrowing History",
        border_style="bright_cyan",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Book",
        ratio=4,
        overflow="fold",
    )

    table.add_column(
        "Author",
        ratio=3,
        overflow="fold",
    )

    table.add_column(
        "Borrowed",
        ratio=2,
    )

    table.add_column(
        "Due",
        ratio=2,
    )

    table.add_column(
        "Returned",
        ratio=2,
    )

    table.add_column(
        "Fine",
        ratio=1,
        justify="right",
    )

    table.add_column(
        "Fine Status",
        ratio=2,
    )

    for record in result:

        fine = safe_float(
            record.get(
                "fine_amount",
                0.0,
            )
        )

        if fine <= 0:

            status = "[green]No Fine[/green]"

        elif record.get(
            "fine_paid"
        ):

            status = "[green]Paid[/green]"

        else:

            status = "[yellow]Unpaid[/yellow]"

        returned = (

            short_date(
                record.get(
                    "returned_at"
                )
            )

            if record.get(
                "returned_at"
            )

            else

            "Not returned"
        )

        table.add_row(

            str(
                record.get(
                    "book_title",
                    "Unknown",
                )
            ),

            str(
                record.get(
                    "author",
                    "Unknown",
                )
            ),

            short_date(
                record.get(
                    "borrowed_at"
                )
            ),

            short_date(
                record.get(
                    "due_date"
                )
            ),

            returned,

            f"${fine:.2f}",

            status,
        )

    console.print(table)


# ============================================================
# SEARCH MENU
# ============================================================

def menu_search_book():

    console.print(
        Rule(
            "🔎 SEARCH BOOKS",
            style="bright_cyan",
        )
    )

    keyword = Prompt.ask(
        "Enter book title or keyword"
    ).strip()

    if not keyword:

        show_error(
            "Please enter a search keyword."
        )

        return

    try:

        result = search_books(
            keyword
        )

    except Exception as error:

        debug_print(
            "[DEBUG] Search error:",
            repr(error),
        )

        show_error(
            "The book search could not be completed."
        )

        return

    if isinstance(
        result,
        dict,
    ):

        show_tool_error(
            result
        )

        return

    if not result:

        show_info(
            f'No books matching "{keyword}" were found.'
        )

        return

    width = console.size.width

    columns = [

        {
            "header": "ID",
            "ratio": 1,
            "justify": "center",
        },

        {
            "header": "Title",
            "ratio": 4,
            "overflow": "fold",
        },
    ]

    if width >= 100:

        columns.append(
            {
                "header": "Author",
                "ratio": 3,
                "overflow": "fold",
            }
        )

    columns.append(
        {
            "header": "Status",
            "ratio": 2,
            "justify": "center",
        }
    )

    table = Table(
        title=f'Search Results: "{keyword}"',
        border_style="bright_cyan",
        expand=True,
        padding=(0, 1),
    )

    for column in columns:

        table.add_column(
            **column
        )

    for book in result:

        status = (

            "[green]✓ Available[/green]"

            if book.get(
                "available"
            )

            else

            "[red]✕ Unavailable[/red]"
        )

        row = [

            str(
                book.get(
                    "id",
                    "?",
                )
            ),

            str(
                book.get(
                    "title",
                    "Unknown",
                )
            ),
        ]

        if width >= 100:

            row.append(
                str(
                    book.get(
                        "author",
                        "Unknown",
                    )
                )
            )

        row.append(status)

        table.add_row(
            *row
        )

    console.print(table)


# ============================================================
# AVAILABILITY MENU
# ============================================================

def menu_check_availability():

    console.print(
        Rule(
            "📖 CHECK AVAILABILITY",
            style="bright_cyan",
        )
    )

    text = Prompt.ask(
        "Enter book ID"
    ).strip()

    try:

        book_id = int(
            text
        )

    except ValueError:

        show_error(
            "Book ID must be a number."
        )

        return

    try:

        result = check_book_availability(
            book_id
        )

    except Exception as error:

        debug_print(
            "[DEBUG] Availability error:",
            repr(error),
        )

        show_error(
            "The availability check could not be completed."
        )

        return

    if not isinstance(
        result,
        dict,
    ):

        show_error(
            "The availability check failed."
        )

        return

    if result.get(
        "success"
    ) is False:

        show_tool_error(
            result
        )

        return

    status = (

        "[green]✓ Available[/green]"

        if result.get(
            "available"
        )

        else

        "[red]✕ Unavailable[/red]"
    )

    table = Table(
        show_header=False,
        border_style="bright_blue",
        expand=True,
        padding=(0, 1),
    )

    table.add_column(
        "Field",
        ratio=1,
        style="bold cyan",
    )

    table.add_column(
        "Value",
        ratio=3,
        overflow="fold",
    )

    table.add_row(
        "Book ID",
        str(
            result.get(
                "id",
                "?",
            )
        ),
    )

    table.add_row(
        "Title",
        str(
            result.get(
                "title",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Author",
        str(
            result.get(
                "author",
                "Unknown",
            )
        ),
    )

    table.add_row(
        "Status",
        status,
    )

    console.print()

    console.print(
        Panel(
            table,
            title="📖 BOOK INFORMATION",
            border_style="bright_blue",
            padding=(1, 1),
        )
    )


# ============================================================
# BORROW MENU
# ============================================================

def menu_borrow_book():

    if not require_login():
        return

    console.print(
        Rule(
            "📚 BORROW A BOOK",
            style="bright_cyan",
        )
    )

    request = Prompt.ask(
        "Which book would you like to borrow?"
    ).strip()

    if not request:

        show_error(
            "Please enter a book name."
        )

        return

    run_agent(
        request
    )


# ============================================================
# RETURN MENU
# ============================================================

def menu_return_book():

    if not require_login():
        return

    console.print(
        Rule(
            "↩ RETURN A BOOK",
            style="bright_cyan",
        )
    )

    text = Prompt.ask(
        "Enter book ID"
    ).strip()

    try:

        book_id = int(
            text
        )

    except ValueError:

        show_error(
            "Book ID must be a number."
        )

        return

    result = execute_tool(
        "return_book",
        {
            "book_id":
                book_id
        },
    )

    if (

        isinstance(
            result,
            dict,
        )

        and

        result.get(
            "success"
        ) is True

    ):

        show_return_result(
            result
        )

    else:

        show_tool_error(
            result
        )


# ============================================================
# HISTORY MENU
# ============================================================

def menu_borrow_history():

    if not require_login():
        return

    console.print(
        Rule(
            "🕘 BORROWING HISTORY",
            style="bright_cyan",
        )
    )

    result = execute_tool(
        "get_borrow_history",
        {},
    )

    show_borrow_history_result(
        result
    )


# ============================================================
# AVAILABLE BOOKS MENU
# ============================================================

def menu_available_books():

    console.print(
        Rule(
            "✅ AVAILABLE BOOKS",
            style="bright_cyan",
        )
    )

    result = execute_tool(
        "list_available_books",
        {},
    )

    if isinstance(
        result,
        dict,
    ):

        show_tool_error(
            result
        )

        return

    if not result:

        show_info(
            "There are currently no books available."
        )

        return

    width = console.size.width

    columns = [

        {
            "header": "ID",
            "ratio": 1,
            "justify": "center",
        },

        {
            "header": "Title",
            "ratio": 4,
            "overflow": "fold",
        },
    ]

    if width >= 100:

        columns.append(
            {
                "header": "Author",
                "ratio": 3,
                "overflow": "fold",
            }
        )

    columns.append(
        {
            "header": "Status",
            "ratio": 2,
            "justify": "center",
        }
    )

    table = Table(
        title="Books Currently Available",
        border_style="green",
        expand=True,
        padding=(0, 1),
    )

    for column in columns:

        table.add_column(
            **column
        )

    for book in result:

        row = [

            str(
                book.get(
                    "id",
                    "?",
                )
            ),

            str(
                book.get(
                    "title",
                    "Unknown",
                )
            ),
        ]

        if width >= 100:

            row.append(
                str(
                    book.get(
                        "author",
                        "Unknown",
                    )
                )
            )

        row.append(
            "[green]✓ Available[/green]"
        )

        table.add_row(
            *row
        )

    console.print(table)


# ============================================================
# CURRENT BORROWED MENU
# ============================================================

def menu_current_borrowed_books():

    if not require_login():
        return

    console.print(
        Rule(
            "📌 MY BORROWED BOOKS",
            style="bright_cyan",
        )
    )

    result = execute_tool(
        "get_current_borrowed_books",
        {},
    )

    show_current_borrowed_books_result(
        result
    )


# ============================================================
# OVERDUE MENU
# ============================================================

def menu_overdue_books():

    if not require_login():
        return

    console.print(
        Rule(
            "⏰ MY OVERDUE BOOKS",
            style="bright_cyan",
        )
    )

    result = execute_tool(
        "get_overdue_books",
        {},
    )

    show_overdue_books_result(
        result
    )


# ============================================================
# FINES MENU
# ============================================================

def menu_fines():

    if not require_login():
        return

    console.print(
        Rule(
            "💰 MY FINES",
            style="bright_cyan",
        )
    )

    result = execute_tool(
        "get_unpaid_fines",
        {},
    )

    show_unpaid_fines_result(
        result
    )


# ============================================================
# AI CHAT MODE
# ============================================================

def ai_chat_mode():

    if not require_login():

        return "back"

    console.print()

    console.print(

        Panel(

            (
                "[bold]AI Library Agent Chat[/bold]\n\n"

                "Ask me about:\n\n"

                "• books\n"
                "• availability\n"
                "• borrowing\n"
                "• returning\n"
                "• due dates\n"
                "• overdue books\n"
                "• fines\n"
                "• payments\n"
                "• recommendations\n"
                "• borrowing history\n\n"

                "[yellow]back[/yellow] → "
                "return to main menu\n"

                "[yellow]exit[/yellow] → "
                "close the application"
            ),

            title="🤖 AI CHAT MODE",

            border_style="bright_blue",

            padding=(1, 2),
        )
    )

    while True:

        try:

            user_input = Prompt.ask(
                "[bold bright_cyan]You[/bold bright_cyan]"
            ).strip()

        except KeyboardInterrupt:

            return "exit"

        if not user_input:
            continue

        command = user_input.lower()

        if command == "back":
            return "back"

        if command in {
            "exit",
            "quit",
        }:

            return "exit"

        run_agent(
            user_input
        )


# ============================================================
# RUN AGENT
# ============================================================

def run_agent(
    user_request,
):

    global messages

    if not require_login():
        return

    # ========================================================
    # ALTERNATIVE CONFIRMATION
    # ========================================================

    if (
        state.waiting_for_confirmation
        and
        not state.completed
    ):

        if is_yes_response(
            user_request
        ):

            state.clear_confirmation()

            show_agent_action(
                "Looking for an available alternative..."
            )

            result = execute_tool(
                "list_available_books",
                {},
            )

            if not isinstance(
                result,
                list,
            ):

                show_tool_error(
                    result
                )

                state.complete()

                return

            if not result:

                show_info(
                    "There are currently no books "
                    "available as an alternative."
                )

                state.complete()

                return

            alternative = select_alternative(
                result,
                state.requested_book_id,
            )

            if alternative is None:

                show_info(
                    "No suitable alternative is "
                    "currently available."
                )

                state.complete()

                return

            state.set_alternative(
                alternative
            )

            show_agent_action(
                (
                    "Selected alternative: "
                    f'{alternative.get("title", "Unknown")}'
                )
            )

            show_agent_action(
                "Processing the borrowing request..."
            )

            borrow_result = execute_tool(
                "borrow_book",
                {
                    "book_id":
                        alternative.get("id")
                },
            )

            if (
                isinstance(
                    borrow_result,
                    dict,
                )
                and
                borrow_result.get(
                    "success"
                ) is True
            ):

                state.set_loan_dates(

                    borrowed_at=
                        borrow_result.get(
                            "borrowed_at"
                        ),

                    due_date=
                        borrow_result.get(
                            "due_date"
                        ),
                )

                state.complete()

                show_borrow_result(
                    state,
                    borrow_result,
                )

                book = borrow_result.get(
                    "book",
                    {}
                )

                if not isinstance(
                    book,
                    dict
                ):

                    book = {}

                add_assistant_history(
                    (
                        "The user successfully borrowed "
                        f'the alternative book '
                        f'"{book.get("title", "Unknown")}".'
                    )
                )

                return

            show_tool_error(
                borrow_result
            )

            state.complete()

            return

        if is_no_response(
            user_request
        ):

            state.clear_confirmation()

            state.complete()

            show_info(
                "Okay. I will not search for an alternative."
            )

            add_assistant_history(
                "The user declined the alternative."
            )

            return

    # ========================================================
    # START NEW TASK
    # ========================================================

    if state.completed:
        state.reset_task()

    state.goal = user_request

    trim_messages()

    messages.append(
        {
            "role":
                "user",
            "content":
                user_request,
        }
    )

    used_tool_calls = set()

    # ========================================================
    # AGENT LOOP
    # ========================================================

    for step in range(
        1,
        MAX_STEPS + 1,
    ):

        debug_print()

        debug_print(
            "=" * 60
        )

        debug_print(
            f"[DEBUG] Agent Step {step}"
        )

        debug_print(
            "[DEBUG] State:",
            state.show()
        )

        # ====================================================
        # API REQUEST
        # ====================================================

        try:

            response = (
                client
                .chat
                .completions
                .create(
                    model="deepseek-v4-flash",
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    extra_body={
                        "thinking": {
                            "type": "enabled"
                        }
                    }
                )
            )

        except Exception as error:

            debug_print(
                "[DEBUG] AI API error:",
                repr(error)
            )

            show_error(
                (
                    "The AI service is temporarily unavailable.\n"
                    "You can continue using the library menu."
                )
            )

            return

        if not response.choices:

            show_error(
                "The AI service returned an empty response."
            )

            return

        message = (
            response
            .choices[0]
            .message
        )

        # ====================================================
        # PRESERVE ASSISTANT MESSAGE
        # ====================================================

        messages.append(
            build_assistant_message(
                message
            )
        )

        # ====================================================
        # FINAL AI ANSWER
        # ====================================================

        if not message.tool_calls:

            if message.content:

                console.print()

                console.print(

                    Panel(
                        message.content,
                        title="🤖 AI AGENT",
                        border_style="bright_blue",
                        padding=(1, 2),
                    )

                )

            return

        # ====================================================
        # TOOL CALLS
        # ====================================================

        tool_results = []

        for tool_call in message.tool_calls:

            function_name = (
                tool_call
                .function
                .name
            )

            raw_arguments = (
                tool_call
                .function
                .arguments
            )

            # ------------------------------------------------
            # PARSE JSON
            # ------------------------------------------------

            try:

                arguments = json.loads(
                    raw_arguments
                )

            except (
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as error:

                debug_print(
                    "[DEBUG] Invalid tool arguments:",
                    repr(error),
                )

                result = {

                    "success":
                        False,

                    "error_type":
                        "ValidationError",

                    "message":
                        "The AI generated invalid tool parameters.",

                    "_debug_error":
                        repr(error),
                }

                tool_results.append({

                    "tool_call":
                        tool_call,

                    "function_name":
                        function_name,

                    "result":
                        result,

                    "is_error":
                        True,
                })

                continue

            if not isinstance(
                arguments,
                dict,
            ):

                result = {

                    "success":
                        False,

                    "error_type":
                        "ValidationError",

                    "message":
                        "The AI generated invalid tool parameters.",
                }

                tool_results.append({

                    "tool_call":
                        tool_call,

                    "function_name":
                        function_name,

                    "result":
                        result,

                    "is_error":
                        True,
                })

                continue

            # ------------------------------------------------
            # DUPLICATE PROTECTION
            # ------------------------------------------------

            signature = (

                function_name,

                json.dumps(
                    arguments,
                    sort_keys=True,
                )
            )

            if signature in used_tool_calls:

                result = {

                    "success":
                        False,

                    "error_type":
                        "ToolError",

                    "message":
                        "Duplicate tool call blocked.",
                }

            else:

                used_tool_calls.add(
                    signature
                )

                action = get_action_message(
                    function_name
                )

                if action:

                    show_agent_action(
                        action
                    )

                result = execute_tool(
                    function_name,
                    arguments
                )

            tool_results.append({

                "tool_call":
                    tool_call,

                "function_name":
                    function_name,

                "result":
                    result,

                "is_error":
                    (
                        isinstance(
                            result,
                            dict,
                        )
                        and
                        result.get(
                            "success"
                        ) is False
                    ),
            })

        # ====================================================
        # TOOL MESSAGES
        # ====================================================

        for item in tool_results:

            tool_call = item[
                "tool_call"
            ]

            result = item[
                "result"
            ]

            messages.append({

                "role":
                    "tool",

                "tool_call_id":
                    tool_call.id,

                "content":
                    json.dumps(
                        result,
                        ensure_ascii=False,
                    ),
            })

        # ====================================================
        # RESULT TRACKING
        # ====================================================

        first_error = None

        direct_query_function = None

        direct_query_result = None

        successful_write_function = None

        successful_write_result = None

        for item in tool_results:

            function_name = item[
                "function_name"
            ]

            result = item[
                "result"
            ]

            # ------------------------------------------------
            # ERROR
            # ------------------------------------------------

            if (
                item["is_error"]
                and
                first_error is None
            ):

                first_error = result

            # ------------------------------------------------
            # SEARCH
            # ------------------------------------------------

            if function_name == "search_books":

                state.last_action = (
                    "search_books"
                )

                if (
                    isinstance(
                        result,
                        list,
                    )
                    and
                    result
                    and
                    state.requested_book is None
                ):

                    state.update_requested_book(
                        result[0]
                    )

            # ------------------------------------------------
            # AVAILABILITY
            # ------------------------------------------------

            elif function_name == "check_book_availability":

                state.last_action = (
                    "check_book_availability"
                )

                if (
                    isinstance(
                        result,
                        dict,
                    )
                    and
                    result.get(
                        "success"
                    ) is True
                ):

                    if hasattr(
                        state,
                        "update_requested_book_from_result"
                    ):

                        state.update_requested_book_from_result(
                            result
                        )

                    else:

                        state.update_requested_book(
                            result
                        )

                    state.update_requested_book_availability(
                        result.get(
                            "available"
                        )
                    )

                    if result.get(
                        "available"
                    ) is False:

                        lower_request = (
                            user_request.lower()
                        )

                        alternative_requested = any(

                            phrase in lower_request

                            for phrase in [

                                "alternative",
                                "another",
                                "different book",
                                "similar book",
                                "find another",
                                "find an alternative",
                                "instead",

                            ]
                        )

                        if not alternative_requested:

                            state.wait_for_confirmation()

            # ------------------------------------------------
            # BORROW
            # ------------------------------------------------

            elif function_name == "borrow_book":

                state.last_action = (
                    "borrow_book"
                )

                if (
                    isinstance(
                        result,
                        dict,
                    )
                    and
                    result.get(
                        "success"
                    ) is True
                ):

                    state.set_loan_dates(

                        borrowed_at=
                            result.get(
                                "borrowed_at"
                            ),

                        due_date=
                            result.get(
                                "due_date"
                            ),
                    )

                    state.complete()

                    successful_write_function = (
                        "borrow_book"
                    )

                    successful_write_result = (
                        result
                    )

            # ------------------------------------------------
            # RETURN
            # ------------------------------------------------

            elif function_name == "return_book":

                state.last_action = (
                    "return_book"
                )

                if (
                    isinstance(
                        result,
                        dict,
                    )
                    and
                    result.get(
                        "success"
                    ) is True
                ):

                    state.set_loan_dates(

                        borrowed_at=
                            result.get(
                                "borrowed_at"
                            ),

                        due_date=
                            result.get(
                                "due_date"
                            ),

                        returned_at=
                            result.get(
                                "returned_at"
                            ),
                    )

                    state.set_overdue_status(

                        result.get(
                            "is_overdue",
                            False,
                        ),

                        result.get(
                            "late_days",
                            0,
                        ),
                    )

                    state.set_fine(

                        result.get(
                            "fine_amount",
                            0.0,
                        ),

                        False,
                    )

                    state.complete()

                    successful_write_function = (
                        "return_book"
                    )

                    successful_write_result = (
                        result
                    )

            # ------------------------------------------------
            # PAYMENT
            # ------------------------------------------------

            elif function_name == "pay_fine":

                state.last_action = (
                    "pay_fine"
                )

                if (
                    isinstance(
                        result,
                        dict,
                    )
                    and
                    result.get(
                        "success"
                    ) is True
                ):

                    state.set_fine(

                        result.get(
                            "fine_amount",
                            0.0,
                        ),

                        True,

                        result.get(
                            "fine_paid_at"
                        ),
                    )

                    state.set_payment(

                        result.get(
                            "payment_amount",
                            result.get(
                                "fine_amount",
                                0.0,
                            ),
                        ),

                        result.get(
                            "payment_status",
                            "Paid",
                        ),
                    )

                    state.complete()

                    successful_write_function = (
                        "pay_fine"
                    )

                    successful_write_result = (
                        result
                    )

            # ------------------------------------------------
            # DIRECT QUERY
            # ------------------------------------------------

            elif function_name in {

                "get_current_borrowed_books",
                "get_overdue_books",
                "get_book_loan_details",
                "calculate_fine",
                "get_unpaid_fines",
                "get_borrow_history",

            }:

                direct_query_function = (
                    function_name
                )

                direct_query_result = (
                    result
                )

            # ------------------------------------------------
            # AVAILABLE BOOKS
            # ------------------------------------------------

            elif function_name == "list_available_books":

                state.last_action = (
                    "list_available_books"
                )

        # ====================================================
        # SUCCESSFUL BORROW
        # ====================================================

        if successful_write_function == "borrow_book":

            show_borrow_result(
                state,
                successful_write_result,
            )

            book = successful_write_result.get(
                "book",
                {},
            )

            if not isinstance(
                book,
                dict,
            ):

                book = {}

            add_assistant_history(

                (
                    f'I successfully borrowed '
                    f'"{book.get("title", "Unknown")}".'
                )

            )

            return

        # ====================================================
        # SUCCESSFUL RETURN
        # ====================================================

        if successful_write_function == "return_book":

            show_return_result(
                successful_write_result
            )

            book = successful_write_result.get(
                "book",
                {},
            )

            if not isinstance(
                book,
                dict,
            ):

                book = {}

            amount = safe_float(

                successful_write_result.get(
                    "fine_amount",
                    0.0,
                )
            )

            if amount > 0:

                summary = (

                    f'I successfully returned '
                    f'"{book.get("title", "Unknown")}". '
                    f'The final fine is '
                    f'${amount:.2f} and it is unpaid.'
                )

            else:

                summary = (

                    f'I successfully returned '
                    f'"{book.get("title", "Unknown")}". '
                    f'There is no fine.'
                )

            add_assistant_history(
                summary
            )

            return

        # ====================================================
        # SUCCESSFUL PAYMENT
        # ====================================================

        if successful_write_function == "pay_fine":

            show_payment_result(
                successful_write_result
            )

            book = successful_write_result.get(
                "book",
                {},
            )

            if not isinstance(
                book,
                dict,
            ):

                book = {}

            amount = safe_float(

                successful_write_result.get(
                    "payment_amount",
                    successful_write_result.get(
                        "fine_amount",
                        0.0,
                    ),
                )
            )

            add_assistant_history(

                (
                    f'The fine for '
                    f'"{book.get("title", "Unknown")}" '
                    f'was successfully paid. '
                    f'Payment amount: '
                    f'${amount:.2f}.'
                )
            )

            return

        # ====================================================
        # CURRENT BORROWED BOOKS
        # ====================================================

        if direct_query_function == (
            "get_current_borrowed_books"
        ):

            show_current_borrowed_books_result(
                direct_query_result
            )

            if isinstance(
                direct_query_result,
                list,
            ):

                add_assistant_history(

                    (
                        f'The user currently has '
                        f'{len(direct_query_result)} '
                        f'borrowed book(s).'
                    )
                )

            return

        # ====================================================
        # OVERDUE
        # ====================================================

        if direct_query_function == (
            "get_overdue_books"
        ):

            show_overdue_books_result(
                direct_query_result
            )

            if isinstance(
                direct_query_result,
                list,
            ):

                add_assistant_history(

                    (
                        f'The user currently has '
                        f'{len(direct_query_result)} '
                        f'overdue book(s).'
                    )
                )

            return

        # ====================================================
        # LOAN DETAILS
        # ====================================================

        if direct_query_function == (
            "get_book_loan_details"
        ):

            show_fine_result(
                direct_query_result
            )

            if (
                isinstance(
                    direct_query_result,
                    dict,
                )
                and
                direct_query_result.get(
                    "success"
                ) is True
            ):

                title = direct_query_result.get(
                    "book_title",
                    "the book",
                )

                add_assistant_history(

                    (
                        f'Loan information for '
                        f'"{title}" was retrieved.'
                    )
                )

            return

        # ====================================================
        # CALCULATE FINE
        # ====================================================

        if direct_query_function == (
            "calculate_fine"
        ):

            show_fine_result(
                direct_query_result
            )

            if (
                isinstance(
                    direct_query_result,
                    dict,
                )
                and
                direct_query_result.get(
                    "success"
                ) is True
            ):

                title = direct_query_result.get(
                    "book_title",
                    "the book",
                )

                amount = safe_float(

                    direct_query_result.get(
                        "fine_amount",
                        0.0,
                    )
                )

                add_assistant_history(

                    (
                        f'The fine for '
                        f'"{title}" is '
                        f'${amount:.2f}.'
                    )
                )

            return

        # ====================================================
        # UNPAID FINES
        # ====================================================

        if direct_query_function == (
            "get_unpaid_fines"
        ):

            show_unpaid_fines_result(
                direct_query_result
            )

            if (
                isinstance(
                    direct_query_result,
                    dict,
                )
                and
                direct_query_result.get(
                    "success"
                ) is True
            ):

                fines = direct_query_result.get(
                    "fines",
                    []
                )

                total = safe_float(

                    direct_query_result.get(
                        "total_fine",
                        0.0,
                    )
                )

                add_assistant_history(

                    (
                        f'The user has '
                        f'{len(fines)} unpaid fine(s) '
                        f'totalling '
                        f'${total:.2f}.'
                    )
                )

            return

        # ====================================================
        # BORROW HISTORY
        # ====================================================

        if direct_query_function == (
            "get_borrow_history"
        ):

            show_borrow_history_result(
                direct_query_result
            )

            if isinstance(
                direct_query_result,
                list,
            ):

                add_assistant_history(

                    (
                        f'The user has '
                        f'{len(direct_query_result)} '
                        f'loan record(s) in their history.'
                    )
                )

            return

        # ====================================================
        # TOOL ERROR
        # ====================================================

        if first_error is not None:

            show_tool_error(
                first_error
            )

            if isinstance(
                first_error,
                dict,
            ):

                add_assistant_history(

                    first_error.get(
                        "message",
                        "The library operation failed.",
                    )
                )

            return

        # ====================================================
        # ALTERNATIVE CONFIRMATION
        # ====================================================

        if (
            state.waiting_for_confirmation
            and
            not state.completed
        ):

            requested_title = (

                state.requested_book

                or

                "The requested book"
            )

            console.print()

            console.print(

                Panel(

                    (
                        f'"{requested_title}" '
                        f'is currently unavailable.\n\n'
                        f'Would you like me to find an '
                        f'available alternative?'
                    ),

                    title="📖 BOOK UNAVAILABLE",

                    border_style="yellow",

                    padding=(1, 2),
                )
            )

            return

    # ========================================================
    # MAX STEPS
    # ========================================================

    show_error(

        "I could not complete the request within "
        "the allowed number of steps."
    )


# ============================================================
# AUTH MENU
# ============================================================

def show_auth_menu():

    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
    )

    table.add_column(
        "Option",
        justify="center",
        style="bold bright_yellow",
    )

    table.add_column(
        "Action"
    )

    for option, action in [

        ("1", "🔐 Login"),
        ("2", "📝 Register"),
        ("3", "🧪 Continue as Demo"),
        ("4", "🚪 Exit"),

    ]:

        table.add_row(
            option,
            action,
        )

    console.print(

        Panel(

            table,

            title="[bold bright_cyan]WELCOME[/bold bright_cyan]",

            border_style="bright_cyan",

            padding=(1, 2),
        )
    )


# ============================================================
# MAIN MENU
# ============================================================

def show_main_menu():

    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
    )

    table.add_column(
        "Option",
        justify="center",
        style="bold bright_yellow",
    )

    table.add_column(
        "Action"
    )

    for option, action in [

        ("1", "🔎 Search for a book"),
        ("2", "📖 Check book availability"),
        ("3", "📚 Borrow a book"),
        ("4", "↩ Return a book"),
        ("5", "🕘 View borrowing history"),
        ("6", "✅ View available books"),
        ("7", "💰 View fines"),
        ("8", "📌 My current borrowed books"),
        ("9", "⏰ My overdue books"),
        ("10", "🤖 Chat with AI Agent"),
        ("11", "🔓 Logout"),

    ]:

        table.add_row(
            option,
            action,
        )

    console.print(

        Panel(

            table,

            title="[bold bright_cyan]MAIN MENU[/bold bright_cyan]",

            border_style="bright_cyan",

            padding=(1, 2),
        )
    )


# ============================================================
# HEADER
# ============================================================

def show_header():

    console.clear()

    console.print()

    user_text = "Not logged in"

    if state.is_logged_in():

        user_text = (

            state.current_user_name

            or

            state.current_username

            or

            "User"
        )

    console.print(

        Panel(

            Align.center(

                Text.from_markup(

                    "[bold bright_white]"
                    "📚 AI LIBRARY AGENT"
                    "[/bold bright_white]\n"

                    "[dim]"
                    "Intelligent Library Assistant"
                    "[/dim]\n\n"

                    "[bright_cyan]User:[/bright_cyan] "
                    f"{user_text}"
                )
            ),

            border_style="bright_blue",

            padding=(1, 3),
        )
    )


# ============================================================
# AUTHENTICATED USER
# ============================================================

def set_authenticated_user(
    user
):

    if not isinstance(
        user,
        dict,
    ):

        return False

    state.reset_all()

    reset_conversation()

    state.set_current_user(

        user_id=
            user.get("id"),

        username=
            user.get("username"),

        full_name=
            user.get("full_name"),
    )

    return state.is_logged_in()


# ============================================================
# LOGIN
# ============================================================

def login_user():

    username = Prompt.ask(
        "Username"
    ).strip()

    if not username:

        show_error(
            "Username cannot be empty."
        )

        return False

    password = Prompt.ask(
        "Password",
        password=True,
    )

    try:

        result = authenticate_user(
            username,
            password,
        )

    except Exception as error:

        debug_print(
            "[DEBUG] Login error:",
            repr(error),
        )

        show_error(
            "The login service is temporarily unavailable."
        )

        return False

    if (
        not isinstance(
            result,
            dict,
        )
        or
        result.get(
            "success"
        ) is not True
    ):

        show_error(

            result.get(
                "message",
                "Login failed.",
            )

            if isinstance(
                result,
                dict,
            )

            else
            "Login failed."
        )

        return False

    if not set_authenticated_user(
        result.get(
            "user",
            {}
        )
    ):

        show_error(
            "The account information could not be loaded."
        )

        return False

    show_success(

        (
            f'Welcome back, '
            f'{state.current_user_name or state.current_username or "User"}!'
        )
    )

    return True


# ============================================================
# DEMO LOGIN
# ============================================================

def login_demo():

    try:

        result = login_demo_user()

    except Exception as error:

        debug_print(
            "[DEBUG] Demo login error:",
            repr(error),
        )

        show_error(
            "The demo account could not be loaded."
        )

        return False

    if (
        not isinstance(
            result,
            dict,
        )
        or
        result.get(
            "success"
        ) is not True
    ):

        show_error(

            result.get(
                "message",
                "Demo login failed.",
            )

            if isinstance(
                result,
                dict,
            )

            else
            "Demo login failed."
        )

        return False

    if not set_authenticated_user(
        result.get(
            "user",
            {}
        )
    ):

        show_error(
            "Demo account information could not be loaded."
        )

        return False

    show_success(
        "Demo account activated."
    )

    return True


# ============================================================
# REGISTER
# ============================================================

def register_account():

    console.print()

    console.print(

        Rule(
            "📝 CREATE ACCOUNT",
            style="bright_cyan",
        )
    )

    full_name = Prompt.ask(
        "Full name"
    ).strip()

    username = Prompt.ask(
        "Username"
    ).strip()

    password = Prompt.ask(
        "Password",
        password=True,
    )

    confirm_password = Prompt.ask(
        "Confirm password",
        password=True,
    )

    if password != confirm_password:

        show_error(
            "Passwords do not match."
        )

        return False

    email = Prompt.ask(
        "Email (optional)",
        default="",
    ).strip()

    if not email:
        email = None

    try:

        result = register_user(

            username=username,

            password=password,

            full_name=full_name,

            email=email,
        )

    except Exception as error:

        debug_print(
            "[DEBUG] Registration error:",
            repr(error),
        )

        show_error(
            "The registration service is temporarily unavailable."
        )

        return False

    if (
        not isinstance(
            result,
            dict,
        )
        or
        result.get(
            "success"
        ) is not True
    ):

        show_error(

            result.get(
                "message",
                "Registration failed.",
            )

            if isinstance(
                result,
                dict,
            )

            else
            "Registration failed."
        )

        return False

    if not set_authenticated_user(
        result.get(
            "user",
            {}
        )
    ):

        show_error(
            "The new account information could not be loaded."
        )

        return False

    show_success(

        (
            "Account created successfully.\n\n"
            f'Welcome, '
            f'{state.current_user_name or state.current_username or "User"}!'
        )
    )

    return True


# ============================================================
# LOGOUT
# ============================================================

def logout_user():

    username = (

        state.current_username

        or

        "User"
    )

    state.reset_all()

    reset_conversation()

    show_info(

        f'"{username}" has been logged out successfully.'
    )


# ============================================================
# MAIN APPLICATION
# ============================================================

def main():

    while True:

        # ====================================================
        # AUTH SCREEN
        # ====================================================

        while not state.is_logged_in():

            show_header()

            show_auth_menu()

            choice = Prompt.ask(

                "Select an option",

                choices=[
                    "1",
                    "2",
                    "3",
                    "4",
                ],
            )

            console.print()

            if choice == "1":

                login_user()

            elif choice == "2":

                register_account()

            elif choice == "3":

                login_demo()

            elif choice == "4":

                console.print()

                console.print(

                    Panel(

                        Align.center(

                            Text(

                                "Thank you for using "
                                "AI Library Agent.\n\n"
                                "Goodbye! 👋",

                                style="bold",
                            )
                        ),

                        border_style="bright_blue",

                        padding=(1, 3),
                    )
                )

                return

            if not state.is_logged_in():

                console.print()

                Prompt.ask(

                    "[dim]Press Enter to continue[/dim]",

                    default="",
                )

        # ====================================================
        # MAIN MENU
        # ====================================================

        while state.is_logged_in():

            show_header()

            show_main_menu()

            choice = Prompt.ask(

                "Select an option",

                choices=[

                    "1",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                    "11",

                ],
            )

            console.print()

            if choice == "1":

                menu_search_book()

            elif choice == "2":

                menu_check_availability()

            elif choice == "3":

                menu_borrow_book()

            elif choice == "4":

                menu_return_book()

            elif choice == "5":

                menu_borrow_history()

            elif choice == "6":

                menu_available_books()

            elif choice == "7":

                menu_fines()

            elif choice == "8":

                menu_current_borrowed_books()

            elif choice == "9":

                menu_overdue_books()

            elif choice == "10":

                result = ai_chat_mode()

                if result == "exit":

                    return

            elif choice == "11":

                logout_user()

                continue

            console.print()

            if state.is_logged_in():

                Prompt.ask(

                    "[dim]"
                    "Press Enter to return to the main menu"
                    "[/dim]",

                    default="",
                )


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        console.print(
            "\n\n[bold]Goodbye! 👋[/bold]"
        )

    except Exception as error:

        if DEBUG_MODE:

            console.print_exception()

            debug_print(
                "[DEBUG] Fatal application error:",
                repr(error),
            )

        else:

            show_error(
                get_user_error_message(
                    error
                )
            )