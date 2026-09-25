"""The agent loop: tool dispatch, event stream and failure rollback."""

import json

from types import SimpleNamespace

import pytest

from agent import core
from agent.core import LibraryAgent


class FakeCompletions:

    def __init__(
        self,
        responses,
    ):

        self._responses = list(
            responses
        )

        self.requests = []

    def create(self, **kwargs):

        self.requests.append(
            kwargs
        )

        response = self._responses.pop(0)

        if isinstance(
            response,
            Exception
        ):

            raise response

        return response


def build_response(
    content=None,
    tool_calls=None,
    reasoning_content=None,
):

    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=message
            )
        ],
        usage=None,
    )


def build_tool_call(
    name,
    arguments,
    call_id="call_1",
):

    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


@pytest.fixture()
def install_fake_llm(
    monkeypatch,
    app_database,
):
    """Replace the DeepSeek client with a scripted fake."""

    completions = {}

    def install(responses):

        fake = FakeCompletions(
            responses
        )

        completions["fake"] = fake

        monkeypatch.setattr(
            core,
            "OpenAI",
            lambda **kwargs: SimpleNamespace(
                chat=SimpleNamespace(
                    completions=fake
                )
            ),
        )

        return fake

    return install


def test_chat_runs_a_tool_then_answers(
    new_user,
    install_fake_llm,
):

    install_fake_llm(
        [
            build_response(
                tool_calls=[
                    build_tool_call(
                        "list_available_books",
                        "{}",
                    )
                ]
            ),
            build_response(
                content="Here are the available books."
            ),
        ]
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    reply = agent.chat(
        "What is available?"
    )

    assert reply == "Here are the available books."

    roles = [
        message["role"]
        for message in agent.messages
    ]

    assert roles == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


def test_chat_rejects_an_empty_message(
    new_user,
    install_fake_llm,
):

    install_fake_llm([])

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    with pytest.raises(ValueError):

        agent.chat("   ")


def test_failed_turn_is_rolled_back(
    new_user,
    install_fake_llm,
):

    install_fake_llm(
        [
            RuntimeError("upstream is down"),
        ]
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    with pytest.raises(RuntimeError):

        agent.chat("hello")

    assert len(agent.messages) == 1


def test_chat_stream_reports_progress_then_final(
    new_user,
    install_fake_llm,
):

    install_fake_llm(
        [
            build_response(
                tool_calls=[
                    build_tool_call(
                        "list_available_books",
                        "{}",
                    )
                ]
            ),
            build_response(
                content="Done."
            ),
        ]
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    events = list(
        agent.chat_stream(
            "What is available?"
        )
    )

    assert [
        event["type"]
        for event in events
    ] == [
        "agent_start",
        "tool_start",
        "tool_result",
        "final",
    ]

    assert events[-1]["message"] == "Done."


def test_invalid_tool_arguments_are_reported_and_not_fatal(
    new_user,
    install_fake_llm,
):

    install_fake_llm(
        [
            build_response(
                tool_calls=[
                    build_tool_call(
                        "list_available_books",
                        "{not json",
                    )
                ]
            ),
            build_response(
                content="Sorry, let me try again."
            ),
        ]
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    events = list(
        agent.chat_stream("go")
    )

    assert [
        event["type"]
        for event in events
    ] == [
        "agent_start",
        "tool_start",
        "tool_error",
        "final",
    ]


def test_chat_stream_reports_failures_as_events(
    new_user,
    install_fake_llm,
):

    install_fake_llm(
        [
            RuntimeError("upstream is down"),
        ]
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    events = list(
        agent.chat_stream("hello")
    )

    assert events[-1]["type"] == "error"

    # The half-finished turn must not leak into the next request.
    assert len(agent.messages) == 1


def test_every_tool_definition_is_well_formed_and_dispatched(
    new_user,
    install_fake_llm,
):
    """A tool that is advertised but not dispatched breaks the loop."""

    install_fake_llm([])

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    assert core.TOOL_DEFINITIONS

    for definition in core.TOOL_DEFINITIONS:

        function = definition["function"]

        name = function["name"]

        assert function["description"], name

        assert (
            function["parameters"]["type"]
            ==
            "object"
        ), name

        result = agent.execute_tool(
            name,
            {
                "book_id": 1,
                "keyword": "python",
            },
        )

        assert not (
            isinstance(
                result,
                dict,
            )
            and
            result.get("message")
            ==
            f"Unknown tool: {name}"
        ), name


def build_rows(count):

    return [
        {
            "loan_id": index,
            "book_title": f"Book {index}",
        }
        for index in range(count)
    ]


def test_short_tool_results_pass_through_unchanged():

    rows = build_rows(3)

    assert core._limit_tool_result(rows) is rows

    assert core._limit_tool_result("short") == "short"


def test_long_lists_are_capped_but_keep_the_total():

    limited = core._limit_tool_result(
        build_rows(40)
    )

    assert limited["total"] == 40
    assert limited["returned"] == core.TOOL_RESULT_ITEM_LIMIT
    assert limited["truncated"] is True
    assert len(limited["items"]) == core.TOOL_RESULT_ITEM_LIMIT


def test_dict_results_keep_their_keys():

    limited = core._limit_tool_result({
        "success": True,
        "message": "ok",
        "fines": build_rows(30),
    })

    assert limited["success"] is True
    assert limited["message"] == "ok"
    assert limited["fines"]["total"] == 30
    assert (
        len(limited["fines"]["items"])
        ==
        core.TOOL_RESULT_ITEM_LIMIT
    )


def test_long_text_fields_are_capped():

    limited = core._limit_tool_result({
        "message": "x" * 5000,
    })

    assert len(limited["message"]) == (
        core.TOOL_RESULT_TEXT_LIMIT
        +
        3
    )

    assert limited["message"].endswith("...")


def test_the_capped_result_is_what_the_model_sees(
    new_user,
    install_fake_llm,
    monkeypatch,
):
    """The guard must sit on the path into the conversation."""

    install_fake_llm(
        [
            build_response(
                tool_calls=[
                    build_tool_call(
                        "get_borrow_history",
                        "{}",
                    )
                ]
            ),
            build_response(
                content="You borrowed 40 books."
            ),
        ]
    )

    monkeypatch.setattr(
        core,
        "get_borrow_history",
        lambda user_id: build_rows(40),
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    agent.chat("show my history")

    tool_message = json.loads(
        agent.messages[-2]["content"]
    )

    assert tool_message["total"] == 40
    assert tool_message["truncated"] is True
    assert (
        len(tool_message["items"])
        ==
        core.TOOL_RESULT_ITEM_LIMIT
    )


def test_agent_stops_at_max_steps(
    new_user,
    install_fake_llm,
):

    install_fake_llm(
        [
            build_response(
                tool_calls=[
                    build_tool_call(
                        "list_available_books",
                        "{}",
                    )
                ]
            )
            for _ in range(core.MAX_STEPS)
        ]
    )

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    events = list(
        agent.chat_stream("go")
    )

    tool_starts = [
        event
        for event in events
        if event["type"] == "tool_start"
    ]

    assert len(tool_starts) == core.MAX_STEPS

    assert events[-1]["type"] == "error"


def test_usage_log_reports_reasoning_tokens(
    new_user,
    install_fake_llm,
    capsys,
):

    install_fake_llm([])

    agent = LibraryAgent(
        user_id=new_user["id"]
    )

    usage = SimpleNamespace(
        prompt_tokens=100,
        prompt_cache_hit_tokens=80,
        prompt_cache_miss_tokens=20,
        completion_tokens=50,
        completion_tokens_details=SimpleNamespace(
            reasoning_tokens=7
        ),
    )

    agent.log_usage(
        SimpleNamespace(
            usage=usage
        ),
        0,
    )

    output = capsys.readouterr().out

    assert "reasoning=7" in output
    assert "cache_hit=80" in output
