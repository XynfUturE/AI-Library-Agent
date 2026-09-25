import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from agent.tools import (
    search_books,
    check_book_availability,
    borrow_book,
    return_book,
    renew_book,
    request_book,
    get_my_holds,
    cancel_hold,
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
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "deepseek-flash"

# Upper bound on LLM calls per user turn. Every step resends the
# system prompt, the tool schemas and the whole conversation, so a
# long loop multiplies the cost of a single question.
MAX_STEPS = 5

# Tool results are replayed into the context on every later step, so
# what the model sees is capped here rather than in each tool: the web
# layer still gets the full data, and one guard covers every tool,
# present and future. A truncated list is reported as
# {"total": n, "returned": k, "truncated": true, "items": [...]}.
TOOL_RESULT_ITEM_LIMIT = 25

TOOL_RESULT_TEXT_LIMIT = 2000

# Only the most recent user turns are resent to the model, so the
# input size of a long conversation stays bounded.
#
# Trimming has a hidden cost: the API matches a cached prompt by
# prefix, so sliding the window on every turn invalidates the whole
# history and it is billed at the full uncached rate again. The
# window is therefore only cut once it grows past the cap, back
# down to MAX_CONVERSATION_USER_TURNS in one go, which keeps most
# turns append-only.
MAX_CONVERSATION_USER_TURNS = 10

MAX_CONVERSATION_USER_TURNS_CAP = 20

# Reasoning mode used for every LLM call.
#   "enabled"  - always reason (default, best quality)
#   "disabled" - never reason (cheapest)
#
# The mode has to stay constant for a whole turn: the API rejects a
# turn that replays an assistant message produced without reasoning
# while reasoning is switched on.
#
# Reasoning effort is deliberately not set: the API already uses
# "high" for ordinary requests, and maps "low"/"medium" to "high"
# anyway, so asking for less would not save anything.
THINKING_MODE = "enabled"

MAX_ARG_PREVIEW_LENGTH = 60

# Friendly progress labels shown while a tool is running.
TOOL_PROGRESS_MESSAGES = {
    "search_books":
        "Searching for the book...",
    "check_book_availability":
        "Checking book availability...",
    "borrow_book":
        "Processing the borrowing request...",
    "return_book":
        "Processing the return request...",
    "renew_book":
        "Renewing the book...",
    "request_book":
        "Checking availability and the queue...",
    "get_my_holds":
        "Checking your holds...",
    "cancel_hold":
        "Withdrawing your request...",
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


# ============================================================
# TOOL ARGUMENT PREVIEW
# ============================================================

def summarize_tool_arguments(
    raw_arguments,
):
    """
    Build a short, UI-safe summary of raw tool arguments.

    The result is only used for the streaming progress UI.
    """

    try:

        arguments = json.loads(
            raw_arguments
        )

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):

        arguments = raw_arguments


    if not isinstance(
        arguments,
        dict,
    ):

        return []


    summary = []

    for key, value in arguments.items():

        text = str(
            value
        )

        if len(
            text
        ) > MAX_ARG_PREVIEW_LENGTH:

            text = (
                text[
                    :MAX_ARG_PREVIEW_LENGTH
                ]
                +
                "..."
            )

        summary.append(
            {
                "name": str(
                    key
                ),
                "value": text,
            }
        )

    return summary


def _sanitize_tool_result(
    result,
):
    """
    Remove internal debug fields before the result is
    serialized back into the LLM conversation context.
    """

    if (
        isinstance(
            result,
            dict,
        )
        and "_debug_error" in result
    ):

        sanitized = dict(
            result
        )

        sanitized.pop(
            "_debug_error"
        )

        return sanitized

    return result


def _limit_list(items):
    """
    Cap a list of tool rows, keeping the real total visible.

    The model still needs to know how many rows exist, otherwise it
    would report a truncated list as the whole answer.
    """

    if len(items) <= TOOL_RESULT_ITEM_LIMIT:

        return items

    return {
        "total": len(items),
        "returned": TOOL_RESULT_ITEM_LIMIT,
        "truncated": True,
        "items": items[
            :TOOL_RESULT_ITEM_LIMIT
        ],
    }


def _limit_tool_result(
    result,
):
    """
    Bound the size of one tool result before it enters the context.

    Only the LLM-facing copy is limited: the web layer calls the same
    tools directly and keeps the complete data.

    ponytail: only top-level lists (and lists one level inside a
    dict) are capped. Deeper nesting would need a recursive walk;
    add it if a tool ever returns list-inside-dict-inside-dict.
    """

    if isinstance(
        result,
        list,
    ):

        return _limit_list(
            result
        )

    if isinstance(
        result,
        dict,
    ):

        limited = {}

        for key, value in result.items():

            if isinstance(
                value,
                list,
            ):

                limited[key] = _limit_list(
                    value
                )

            elif (
                isinstance(
                    value,
                    str,
                )
                and
                len(value) > TOOL_RESULT_TEXT_LIMIT
            ):

                limited[key] = (
                    value[
                        :TOOL_RESULT_TEXT_LIMIT
                    ]
                    +
                    "..."
                )

            else:

                limited[key] = value

        return limited

    if (
        isinstance(
            result,
            str,
        )
        and
        len(result) > TOOL_RESULT_TEXT_LIMIT
    ):

        return (
            result[
                :TOOL_RESULT_TEXT_LIMIT
            ]
            +
            "..."
        )

    return result


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an intelligent AI library assistant.

You help the authenticated library user with:

- searching for books
- checking book availability
- borrowing books
- returning books
- checking current borrowed books
- checking overdue books
- renewing a loan before it is due
- checking fines
- checking unpaid fines
- paying fines
- viewing borrowing history
- viewing available books
- recommending books

GENERAL RULES:

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

Long tool results are truncated. When a list comes back as
{"total": n, "returned": k, "items": [...]}, report the real
total, not the number of rows you can see.

The application supplies the authenticated user's ID.
Never ask the user for a user ID.

--------------------------------------------------
BORROWING
--------------------------------------------------

For title-based borrowing:

1. Use search_books first.
2. Identify the correct actual book.
3. Obtain its real book ID.
4. Check availability.
5. Borrow only when availability is verified.

Never invent a book ID.

Never call borrow_book before availability has been verified.

When an explicit book ID is supplied, check its availability
before borrowing.

--------------------------------------------------
ALTERNATIVE BOOKS
--------------------------------------------------

If the requested book is unavailable:

1. Inform the user that it is unavailable.
2. Ask whether they want an available alternative.
3. Do not automatically replace the requested book.
4. Do not automatically borrow an alternative without
   user confirmation.

--------------------------------------------------
RECOMMENDATIONS
--------------------------------------------------

A recommendation does not automatically mean borrowing.

For recommendations:

1. Use list_available_books.
2. Only recommend real books returned by the tool.
3. Do not invent book information.
4. Do not automatically borrow the recommended book.

--------------------------------------------------
RETURNING
--------------------------------------------------

For return requests:

Use return_book for the authenticated user.

Do not perform an unnecessary availability check.

--------------------------------------------------
CURRENT LOANS
--------------------------------------------------

For current borrowed books:

Use get_current_borrowed_books.

--------------------------------------------------
OVERDUE
--------------------------------------------------

For general overdue questions:

Use get_overdue_books.

For a specific book:

Use get_book_loan_details.

--------------------------------------------------
FINES
--------------------------------------------------

For general unpaid fines:

Use get_unpaid_fines.

For a specific book:

Use calculate_fine or get_book_loan_details.

--------------------------------------------------
PAYMENT
--------------------------------------------------

A fine can only be paid after the related book has been
returned and a final fine has been recorded.

Never pay an estimated active-loan fine.

Never pay another user's fine.

Never pay an already paid fine.

Only claim successful payment when pay_fine returns
success=true.

--------------------------------------------------
BORROWING HISTORY
--------------------------------------------------

Use get_borrow_history.

Do not invent historical records.

The application may render the result using its own UI.

--------------------------------------------------
CONVERSATION CONTEXT
--------------------------------------------------

Understand references such as:

- it
- this book
- that book
- that one
- the recommended one
- your recommendation
- another one

Use previous conversation context when the reference is
unambiguous.

If multiple books could match, ask for clarification.

--------------------------------------------------
ERROR HANDLING
--------------------------------------------------

Do not expose:

- SQL statements
- stack traces
- implementation details
- API keys
- private application information

Keep user-facing responses concise and clear.

--------------------------------------------------
TASK COMPLETION
--------------------------------------------------

Stop using tools once the requested task is complete.

Do not perform unnecessary tool calls.

Never claim an operation succeeded unless the corresponding
tool confirms success.
"""


# ============================================================
# TOOL DEFINITIONS
# ============================================================

TOOL_DEFINITIONS = [

    # --------------------------------------------------------
    # SEARCH BOOKS
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "search_books",
            "description": (
                "Search books by title or author keyword."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "Book title keyword."
                        ),
                    }
                },
                "required": [
                    "keyword"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # CHECK AVAILABILITY
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "check_book_availability",
            "description": (
                "Check whether a specific book is "
                "currently available for borrowing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # BORROW
    # --------------------------------------------------------

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
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

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
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # REQUEST BOOK (HOLD OR PURCHASE SUGGESTION)
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "request_book",
            "description": (
                "Ask for one book that cannot be borrowed right now. "
                "The library queues a hold when it owns the title, or "
                "records a purchase suggestion when it does not. Pass "
                "book_id when a search already found the book, else "
                "the title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": (
                            "Book ID, when known."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": (
                            "Book title, when no ID is known."
                        ),
                    },
                },
            },
        },
    },

    # --------------------------------------------------------
    # MY HOLDS
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "get_my_holds",
            "description": (
                "List the authenticated user's active holds and "
                "purchase suggestions, with queue position."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # --------------------------------------------------------
    # CANCEL HOLD
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "cancel_hold",
            "description": (
                "Withdraw one of the authenticated user's own "
                "holds or purchase suggestions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hold_id": {
                        "type": "integer",
                        "description": (
                            "Hold ID from get_my_holds."
                        ),
                    }
                },
                "required": [
                    "hold_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # CURRENT BORROWED BOOKS
    # --------------------------------------------------------

    # --------------------------------------------------------
    # RENEW
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "renew_book",
            "description": (
                "Extend the due date of a book the "
                "authenticated user currently has borrowed. "
                "Only possible while the loan is not overdue "
                "and the renewal limit is not reached."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # CURRENT BORROWED BOOKS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # OVERDUE
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "get_overdue_books",
            "description": (
                "Get all overdue books belonging "
                "to the authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # --------------------------------------------------------
    # LOAN DETAILS
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "get_book_loan_details",
            "description": (
                "Get active or most recent loan "
                "details for a specific book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # CALCULATE FINE
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "calculate_fine",
            "description": (
                "Calculate the current or final fine "
                "for a specific book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # UNPAID FINES
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "get_unpaid_fines",
            "description": (
                "Get unpaid fines belonging "
                "to the authenticated user."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # --------------------------------------------------------
    # PAY FINE
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "pay_fine",
            "description": (
                "Pay an unpaid final fine for "
                "a returned book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": (
                            "Book ID."
                        ),
                    }
                },
                "required": [
                    "book_id"
                ],
            },
        },
    },

    # --------------------------------------------------------
    # BORROW HISTORY
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # AVAILABLE BOOKS
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "list_available_books",
            "description": (
                "List all books currently available "
                "for borrowing."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ============================================================
# LIBRARY AGENT
# ============================================================

class LibraryAgent:
    """
    Reusable AI Agent.

    Each authenticated Web session should own one
    LibraryAgent instance.

    The Agent stores its own:

    - authenticated user ID
    - DeepSeek client
    - conversation history
    """

    def __init__(
        self,
        user_id: int,
    ):
        # ----------------------------------------------------
        # Validate user ID
        # ----------------------------------------------------

        try:

            self.user_id = int(
                user_id
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                "Invalid user ID."
            )

        # ----------------------------------------------------
        # API key
        # ----------------------------------------------------

        api_key = os.getenv(
            "DEEPSEEK_API_KEY"
        )

        if not api_key:

            raise ValueError(
                "DEEPSEEK_API_KEY is not loaded."
            )

        # ----------------------------------------------------
        # DeepSeek client
        # ----------------------------------------------------

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=60.0,
            # Retry transient upstream failures (429 / 5xx /
            # connection resets) instead of losing the whole turn.
            max_retries=3,
        )

        # ----------------------------------------------------
        # Model
        # ----------------------------------------------------

        self.model = MODEL_NAME

        # ----------------------------------------------------
        # Conversation history
        # ----------------------------------------------------

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

    # ========================================================
    # TRIM CONVERSATION HISTORY
    # ========================================================

    def trim_messages(self):
        """
        Keep only the most recent user turns.

        Without this, every LLM call would resend the whole
        conversation, including old tool results, so the input
        size of a long session would grow without bound.

        The cut is always made on a user message, so the kept
        window never starts with a tool result whose assistant
        message was dropped.

        It only trims once the window grows past the cap, so
        between two cuts the conversation is append-only. An
        append-only prefix keeps matching the API's prompt cache,
        which is billed at a fraction of the uncached rate, while
        trimming on every turn would invalidate it each time.
        """

        user_indexes = [
            index
            for index, message in enumerate(
                self.messages
            )
            if message.get("role") == "user"
        ]

        if len(user_indexes) <= MAX_CONVERSATION_USER_TURNS_CAP:

            return

        first_kept_index = user_indexes[
            -MAX_CONVERSATION_USER_TURNS
        ]

        self.messages = (
            [self.messages[0]]
            + self.messages[first_kept_index:]
        )

    # ========================================================
    # REASONING MODE
    # ========================================================

    def thinking_payload(self):
        """
        Build the reasoning parameter for an LLM call.

        The value stays constant for the whole turn, so an
        assistant message produced without reasoning is never
        replayed back while reasoning is switched on.
        """

        return {
            "thinking": {
                "type": THINKING_MODE
            }
        }

    # ========================================================
    # TOKEN USAGE
    # ========================================================

    def log_usage(
        self,
        response,
        step,
    ):
        """
        Report token usage of one LLM call.

        Cached and uncached input tokens are billed at very
        different rates, so the split is the only way to tell
        whether the conversation prefix is actually being reused.
        """

        usage = getattr(
            response,
            "usage",
            None,
        )

        if usage is None:

            return

        # Reasoning tokens are billed as output, so they are reported
        # separately: without this the completion count looks huge and
        # the cause is invisible.
        details = getattr(
            usage,
            "completion_tokens_details",
            None,
        )

        reasoning = getattr(
            details,
            "reasoning_tokens",
            None,
        )

        if reasoning is None:

            reasoning = getattr(
                usage,
                "reasoning_tokens",
                None,
            )

        print(
            "[usage]"
            f" step={step}"
            f" prompt={getattr(usage, 'prompt_tokens', None)}"
            f" cache_hit={getattr(usage, 'prompt_cache_hit_tokens', None)}"
            f" cache_miss={getattr(usage, 'prompt_cache_miss_tokens', None)}"
            f" completion={getattr(usage, 'completion_tokens', None)}"
            f" reasoning={reasoning}",
            flush=True,
        )

    # ========================================================
    # EXECUTE TOOL
    # ========================================================

    def execute_tool(
        self,
        function_name,
        arguments,
    ):
        """
        Execute a library tool.

        IMPORTANT:

        The LLM never supplies user_id.

        The authenticated user_id stored by this
        Agent is injected here.
        """

        try:

            # ------------------------------------------------
            # SEARCH
            # ------------------------------------------------

            if function_name == "search_books":

                return search_books(
                    arguments["keyword"]
                )

            # ------------------------------------------------
            # AVAILABILITY
            # ------------------------------------------------

            if function_name == "check_book_availability":

                return check_book_availability(
                    arguments["book_id"]
                )

            # ------------------------------------------------
            # BORROW
            # ------------------------------------------------

            if function_name == "borrow_book":

                return borrow_book(
                    arguments["book_id"],
                    self.user_id,
                )

            # ------------------------------------------------
            # RETURN
            # ------------------------------------------------

            if function_name == "return_book":

                return return_book(
                    arguments["book_id"],
                    self.user_id,
                )

            # ------------------------------------------------
            # RENEW
            # ------------------------------------------------

            if function_name == "renew_book":

                return renew_book(
                    arguments["book_id"],
                    self.user_id,
                )

            # ------------------------------------------------
            # REQUEST / QUEUE
            # ------------------------------------------------

            if function_name == "request_book":

                return request_book(
                    self.user_id,
                    arguments.get("book_id"),
                    arguments.get("title"),
                )

            if function_name == "get_my_holds":

                return get_my_holds(
                    self.user_id
                )

            if function_name == "cancel_hold":

                return cancel_hold(
                    self.user_id,
                    arguments["hold_id"],
                )

            # ------------------------------------------------
            # CURRENT LOANS
            # ------------------------------------------------

            if function_name == "get_current_borrowed_books":

                return get_current_borrowed_books(
                    self.user_id
                )

            # ------------------------------------------------
            # OVERDUE
            # ------------------------------------------------

            if function_name == "get_overdue_books":

                return get_overdue_books(
                    self.user_id
                )

            # ------------------------------------------------
            # LOAN DETAILS
            # ------------------------------------------------

            if function_name == "get_book_loan_details":

                return get_book_loan_details(
                    arguments["book_id"],
                    self.user_id,
                )

            # ------------------------------------------------
            # FINE
            # ------------------------------------------------

            if function_name == "calculate_fine":

                return calculate_fine(
                    arguments["book_id"],
                    self.user_id,
                )

            # ------------------------------------------------
            # UNPAID FINES
            # ------------------------------------------------

            if function_name == "get_unpaid_fines":

                return get_unpaid_fines(
                    self.user_id
                )

            # ------------------------------------------------
            # PAY FINE
            # ------------------------------------------------

            if function_name == "pay_fine":

                return pay_fine(
                    arguments["book_id"],
                    self.user_id,
                )

            # ------------------------------------------------
            # HISTORY
            # ------------------------------------------------

            if function_name == "get_borrow_history":

                return get_borrow_history(
                    self.user_id
                )

            # ------------------------------------------------
            # AVAILABLE BOOKS
            # ------------------------------------------------

            if function_name == "list_available_books":

                return list_available_books()

            # ------------------------------------------------
            # UNKNOWN TOOL
            # ------------------------------------------------

            return {
                "success": False,
                "error_type": "ToolError",
                "message": (
                    f"Unknown tool: {function_name}"
                ),
            }

        except KeyError:

            return {
                "success": False,
                "error_type": "ValidationError",
                "message": (
                    "The AI provided incomplete "
                    "information for this operation."
                ),
            }

        except Exception:

            return {
                "success": False,
                "error_type": "ToolError",
                "message": (
                    "The library operation "
                    "could not be completed."
                ),
            }

    # ========================================================
    # BUILD ASSISTANT MESSAGE
    # ========================================================

    @staticmethod
    def build_assistant_message(
        message,
    ):
        """
        Convert an SDK assistant message into the
        message format required for the next API call.

        The reasoning content is replayed too: the API
        documents it as required back for any turn that used
        a tool, even though it tolerates its absence today.
        """

        result = {
            "role": "assistant",
            "content": message.content or "",
        }

        reasoning = getattr(
            message,
            "reasoning_content",
            None,
        )

        if reasoning:

            result["reasoning_content"] = reasoning

        if message.tool_calls:

            result["tool_calls"] = [

                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": (
                            tool_call.function.name
                        ),
                        "arguments": (
                            tool_call.function.arguments
                        ),
                    },
                }

                for tool_call in message.tool_calls
            ]

        return result

    # ========================================================
    # NORMAL CHAT
    # ========================================================

    def chat(
        self,
        user_message: str,
    ) -> str:
        """
        Run a complete Agent interaction.

        This is the non-streaming version used by
        /api/chat.
        """

        # Drop the oldest turns before a new one starts, so the
        # rollback below and the token cost stay bounded.
        self.trim_messages()

        base_len = len(
            self.messages
        )

        try:

            # There is exactly one Agent loop (the generator in
            # _chat_stream_body). The blocking call simply drains
            # it and keeps the final answer.
            for event in self._chat_stream_body(
                user_message
            ):

                if event["type"] == "final":

                    return event["message"]

                if event["type"] == "error":

                    raise RuntimeError(
                        event["message"]
                    )

            raise RuntimeError(
                "The agent could not complete the "
                "request within the allowed number of steps."
            )

        except Exception:

            # Roll back any half-finished turn so a failed
            # request cannot pollute later conversations.
            del self.messages[
                base_len:
            ]

            raise

    # ========================================================
    # STREAMING CHAT
    # ========================================================

    def chat_stream(
        self,
        user_message: str,
    ):
        """
        Run the Agent while yielding progress events.

        The Web layer converts these events into SSE messages.

        Example event:

        {
            "type": "tool_start",
            "message": "Searching for the book..."
        }
        """

        # Drop the oldest turns before a new one starts, so the
        # rollback below and the token cost stay bounded.
        self.trim_messages()

        base_len = len(
            self.messages
        )

        completed = False

        failed = False

        try:

            for event in self._chat_stream_body(
                user_message
            ):

                if event["type"] == "error":

                    failed = True

                yield event

            completed = True

        finally:

            if failed or not completed:

                # Either the stream was closed before it
                # completed (e.g. the client disconnected) or the
                # turn failed: drop the half-finished turn so it
                # cannot pollute later conversations.
                del self.messages[
                    base_len:
                ]

    def _chat_stream_body(
        self,
        user_message: str,
    ):
        """
        Streaming Agent loop (see chat_stream()).
        """

        # ----------------------------------------------------
        # Validate message
        # ----------------------------------------------------

        if not isinstance(
            user_message,
            str,
        ):

            raise TypeError(
                "Message must be a string."
            )

        user_message = user_message.strip()

        if not user_message:

            raise ValueError(
                "Message cannot be empty."
            )

        # ----------------------------------------------------
        # Add user message
        # ----------------------------------------------------

        self.messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # ----------------------------------------------------
        # Start event
        # ----------------------------------------------------

        yield {
            "type": "agent_start",
            "message": "Thinking...",
        }

        # ----------------------------------------------------
        # Agent loop
        # ----------------------------------------------------

        for step in range(
            MAX_STEPS
        ):

            try:

                response = (
                    self.client
                    .chat
                    .completions
                    .create(
                        model=self.model,
                        messages=self.messages,
                        tools=TOOL_DEFINITIONS,
                        tool_choice="auto",
                        extra_body=(
                            self.thinking_payload()
                        ),
                    )
                )

            except Exception:

                # Report upstream failures as an event instead of
                # raising: the caller rolls the turn back and the
                # next request starts from a clean history.
                yield {
                    "type": "error",
                    "message": (
                        "The AI service could not "
                        "complete your request."
                    ),
                }

                return

            self.log_usage(
                response,
                step,
            )

            if not response.choices:

                yield {
                    "type": "error",
                    "message": (
                        "The AI service returned "
                        "an empty response."
                    ),
                }

                return

            message = (
                response
                .choices[0]
                .message
            )

            # ------------------------------------------------
            # Preserve assistant message
            # ------------------------------------------------

            self.messages.append(
                self.build_assistant_message(
                    message
                )
            )

            # ------------------------------------------------
            # Final response
            # ------------------------------------------------

            if not message.tool_calls:

                yield {
                    "type": "final",
                    "message": (
                        message.content
                        or
                        ""
                    ),
                }

                return

            # ------------------------------------------------
            # Process tools
            # ------------------------------------------------

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

                # --------------------------------------------
                # Friendly UI message
                # --------------------------------------------

                tool_messages = TOOL_PROGRESS_MESSAGES

                yield {
                    "type": "tool_start",
                    "message": tool_messages.get(
                        function_name,
                        "Executing library operation...",
                    ),
                    "tool": function_name,
                    "args": summarize_tool_arguments(
                        raw_arguments
                    ),
                }

                # --------------------------------------------
                # Parse tool arguments
                # --------------------------------------------

                try:

                    arguments = json.loads(
                        raw_arguments
                    )

                except (
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                ):

                    result = {
                        "success": False,
                        "error_type":
                            "ValidationError",
                        "message": (
                            "The AI generated "
                            "invalid tool parameters."
                        ),
                    }

                else:

                    if not isinstance(
                        arguments,
                        dict,
                    ):

                        result = {
                            "success": False,
                            "error_type":
                                "ValidationError",
                            "message": (
                                "The AI generated "
                                "invalid tool parameters."
                            ),
                        }

                    else:

                        result = self.execute_tool(
                            function_name,
                            arguments,
                        )

                # --------------------------------------------
                # Save tool result for the next LLM call
                # --------------------------------------------

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": json.dumps(
                            _limit_tool_result(
                                _sanitize_tool_result(
                                    result
                                )
                            ),
                            ensure_ascii=False,
                        ),
                    }
                )

                # --------------------------------------------
                # Report result
                # --------------------------------------------

                if (
                    isinstance(
                        result,
                        dict,
                    )
                    and
                    result.get(
                        "success"
                    ) is False
                ):

                    yield {
                        "type": "tool_error",
                        "message": result.get(
                            "message",
                            "The library operation failed.",
                        ),
                        "tool": function_name,
                    }

                else:

                    yield {
                        "type": "tool_result",
                        "message": (
                            "Library operation completed."
                        ),
                        "tool": function_name,
                    }

        # ----------------------------------------------------
        # Maximum steps exceeded
        # ----------------------------------------------------

        yield {
            "type": "error",
            "message": (
                "The agent could not complete "
                "the request within the allowed "
                "number of steps."
            ),
        }
