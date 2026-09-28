"""Per-turn tracing: one JSON line per LLM step, tool call and turn."""

import json

from agent import trace
from agent.core import LibraryAgent

from test_prompt_injection import (
    build_response,
    build_tool_call,
    install_fake_llm,
)


def read_trace(path):

    return [
        json.loads(
            line
        )
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def test_record_is_a_no_op_without_a_path(monkeypatch):

    monkeypatch.delenv(
        trace.TRACE_PATH_ENV,
        raising=False,
    )

    payload = trace.record(
        "unit_test_event",
        value=1,
    )

    assert payload["event"] == "unit_test_event"

    assert payload["value"] == 1

    assert "ts" in payload


def test_a_turn_writes_llm_tool_and_turn_records(
    tmp_path,
    monkeypatch,
    new_user,
    install_fake_llm,
):

    trace_file = tmp_path / "agent-trace.jsonl"

    monkeypatch.setenv(
        trace.TRACE_PATH_ENV,
        str(trace_file),
    )

    install_fake_llm(
        [
            build_response(
                tool_calls=[
                    build_tool_call(
                        "list_available_books",
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

    assert agent.chat("What is available?") == (
        "Here are the available books."
    )

    records = read_trace(
        trace_file
    )

    events = [
        record["event"]
        for record in records
    ]

    assert events == [
        "llm_step",
        "tool_call",
        "llm_step",
        "turn_end",
    ]

    tool_record = records[1]

    assert tool_record["tool"] == "list_available_books"

    assert tool_record["args"] == []

    # list_available_books returns a list, so there is no success flag;
    # the row count is what a trace reader can act on.
    assert tool_record["success"] is None

    assert tool_record["rows"] >= 1

    assert tool_record["seconds"] >= 0

    assert records[0]["step"] == 0

    assert records[0]["prompt"] is None

    turn = records[-1]

    assert turn["steps"] == 2

    assert turn["answer_chars"] == len(
        "Here are the available books."
    )

    assert turn["seconds"] >= 0


def test_an_upstream_failure_is_traced(
    tmp_path,
    monkeypatch,
    new_user,
    install_fake_llm,
):

    trace_file = tmp_path / "agent-trace.jsonl"

    monkeypatch.setenv(
        trace.TRACE_PATH_ENV,
        str(trace_file),
    )

    install_fake_llm(
        [
            RuntimeError(
                "upstream is down"
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

    assert events[-1]["type"] == "error"

    assert [
        record["event"]
        for record in read_trace(
            trace_file
        )
    ] == [
        "llm_error",
    ]
