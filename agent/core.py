import json
import os

from dotenv import load_dotenv
from openai import OpenAI

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
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "deepseek-v4-flash"

MAX_STEPS = 8

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
        """

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

        base_len = len(
            self.messages
        )

        try:

            return self._chat_body(
                user_message
            )

        except Exception:

            # Roll back any half-finished turn so a failed
            # request cannot pollute later conversations.
            del self.messages[
                base_len:
            ]

            raise

    def _chat_body(
        self,
        user_message: str,
    ):
        """
        Non-streaming Agent loop (see chat()).
        """

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
        # Agent loop
        # ----------------------------------------------------

        for _ in range(
            MAX_STEPS
        ):

            response = (
                self.client
                .chat
                .completions
                .create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    extra_body={
                        "thinking": {
                            "type": "enabled"
                        }
                    },
                )
            )

            if not response.choices:

                raise RuntimeError(
                    "The AI service returned "
                    "an empty response."
                )

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
            # Final answer
            # ------------------------------------------------

            if not message.tool_calls:

                return (
                    message.content
                    or
                    ""
                )

            # ------------------------------------------------
            # Tool calls
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
                # Parse arguments
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
                # Add Tool Result
                # --------------------------------------------

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": json.dumps(
                            _sanitize_tool_result(
                                result
                            ),
                            ensure_ascii=False,
                        ),
                    }
                )

        raise RuntimeError(
            "The agent could not complete the "
            "request within the allowed number of steps."
        )

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

        base_len = len(
            self.messages
        )

        committed = False

        try:

            yield from self._chat_stream_body(
                user_message
            )

            committed = True

        finally:

            if not committed:

                # The stream was closed before it completed
                # (e.g. the client disconnected): drop the
                # half-finished turn from conversation history.
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

        for _ in range(
            MAX_STEPS
        ):

            response = (
                self.client
                .chat
                .completions
                .create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    extra_body={
                        "thinking": {
                            "type": "enabled"
                        }
                    },
                )
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
                            _sanitize_tool_result(
                                result
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