"""Score the agent on tool selection, answer quality, latency and token cost.

    python scripts/eval_agent.py
    python scripts/eval_agent.py --json eval-results.json

Every case is a plain sentence, the tools that would be correct for it,
and optionally what the answer has to contain. The script runs the real
agent (so it needs DEEPSEEK_API_KEY) and reports which tool the agent
reached for first, whether the reply stayed on topic, and what it cost.

Answer checking is deliberately deterministic: no second model grades
the reply. The checks catch the failures that actually matter in a tool
calling agent - a refusal, an internal error message, an empty reply, or
an answer that ignores what the tools returned. Swapping in a
model-as-judge would mean a second paid call per case and a score that
moves between runs; keep it optional if you ever need it.

It runs against a throwaway database, so borrow/pay cases cannot touch
the real one.
"""

import os
import tempfile

# Must happen before the application is imported: the modules read the
# database path at import time.
os.environ["LIBRARY_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="library-eval-"),
    "library.db",
)

import argparse
import contextlib
import io
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
    )
)

from agent import database

from agent.auth import login_demo_user

from agent.core import LibraryAgent


ANSWER_MISS_PATTERNS = [
    r"\bas an ai\b",
    r"i (?:can'?t|cannot|am unable to) (?:help|assist|access)",
    r"i don'?t have (?:the )?access",
    r"something went wrong",
    r"could not complete your request",
    r"internal error",
]


CASES = [
    (
        "Find books by Isaac Asimov",
        {"search_books"},
        {"contains": [r"asimov"]},
    ),
    (
        "What do you have about space and the universe?",
        {"search_books_semantic", "search_books"},
        {"contains": [r"space|universe|cosmos|astronom"]},
    ),
    (
        "Do you have a copy of Clean Code?",
        {"search_books", "check_book_availability"},
        {"contains": [r"clean code"]},
    ),
    (
        "Is book 5 available right now?",
        {"check_book_availability"},
    ),
    (
        "I want to borrow book 3",
        {"borrow_book", "check_book_availability"},
    ),
    (
        "Return my copy of book 3",
        {"return_book", "get_current_borrowed_books"},
    ),
    (
        "Renew book 3 for me",
        {"renew_book"},
    ),
    (
        "What am I currently borrowing?",
        {"get_current_borrowed_books"},
    ),
    (
        "Is anything overdue on my account?",
        {"get_overdue_books", "get_current_borrowed_books"},
    ),
    (
        "Show me the details of my loan for book 7",
        {"get_book_loan_details"},
    ),
    (
        "How much fine do I owe for book 7?",
        {"calculate_fine", "get_book_loan_details"},
        {"contains": [r"fine|owe|overdue"]},
    ),
    (
        "Do I have unpaid fines?",
        {"get_unpaid_fines"},
        {"contains": [r"fine"]},
    ),
    (
        "Pay the fine for book 7",
        {"pay_fine", "get_unpaid_fines"},
    ),
    (
        "Show my borrowing history",
        {"get_borrow_history"},
        {"contains": [r"borrow|loan|history|no record"]},
    ),
    (
        "Which books are on the shelf right now?",
        {"list_available_books"},
        {"contains": [r"available|shelf|on the shelf"]},
    ),
    (
        "Put me in line for book 9",
        {"request_book"},
    ),
    (
        "The library does not own Deep Sea Chronicles, please ask for it",
        {"request_book", "search_books"},
    ),
    (
        "What am I waiting for?",
        {"get_my_holds"},
        {"contains": [r"hold|wait|queue|suggest|no "]},
    ),
    (
        "Cancel my hold number 3",
        {"cancel_hold", "get_my_holds"},
    ),
    (
        "推荐一本讲睡眠与记忆的科普书",
        {"search_books_semantic", "list_available_books"},
    ),
]


def parse_usage(text):
    """Sum the [usage] lines printed by the agent loop."""

    totals = {
        "prompt": 0,
        "completion": 0,
        "reasoning": 0,
        "steps": 0,
    }

    for line in text.splitlines():

        if not line.startswith("[usage]"):

            continue

        totals["steps"] += 1

        for key in ("prompt", "completion", "reasoning"):

            marker = f"{key}="

            position = line.find(marker)

            if position == -1:

                continue

            value = line[
                position + len(marker):
            ].split()[0]

            if value.isdigit():

                totals[key] += int(value)

    return totals


def run_case(user_id, prompt):

    agent = LibraryAgent(
        user_id=user_id
    )

    events = []

    buffer = io.StringIO()

    started = time.perf_counter()

    with contextlib.redirect_stdout(buffer):

        for event in agent.chat_stream(prompt):

            events.append(event)

    elapsed = time.perf_counter() - started

    tools = [
        event["tool"]
        for event in events
        if event["type"] == "tool_start"
    ]

    answer = next(
        (
            event["message"]
            for event in events
            if event["type"] == "final"
        ),
        "",
    )

    errors = [
        event["message"]
        for event in events
        if event["type"] == "error"
    ]

    return {
        "prompt": prompt,
        "answer": answer,
        "tools": tools,
        "error": errors[0] if errors else None,
        "seconds": round(elapsed, 2),
        "usage": parse_usage(buffer.getvalue()),
    }


def answer_checks(case):
    """
    Optional expected-content checks: the third element of a case.
    """

    if len(case) > 2 and case[2]:

        return case[2]

    return {}


def grade_answer(answer, checks):
    """
    Check the reply itself, without a second model.

    A tool calling agent fails quietly in two ways: it refuses, or it
    answers without using what the tools returned. Both are catchable
    with plain patterns, and both are visible in the raw JSON output
    when a case needs a closer look.
    """

    text = (
        answer
        or
        ""
    ).lower()

    problems = []

    if not text.strip():

        problems.append(
            "empty answer"
        )

    patterns = (
        ANSWER_MISS_PATTERNS
        +
        list(
            checks.get(
                "forbidden",
                (),
            )
        )
    )

    for pattern in patterns:

        if re.search(
            pattern,
            text,
        ):

            problems.append(
                f"matched /{pattern}/"
            )

    for pattern in checks.get(
        "contains",
        (),
    ):

        if not re.search(
            pattern,
            text,
        ):

            problems.append(
                f"missing /{pattern}/"
            )

    return {
        "answer_ok": not problems,
        "answer_problems": problems,
    }


def grade(case, result):

    expected = case[1]

    first = result["tools"][0] if result["tools"] else None

    return {
        "expected": sorted(expected),
        "first_tool": first,
        "matched": first in expected,
    }


def main(argv=None):

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--json",
        metavar="PATH",
        help="also write the raw results to this file",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=len(CASES),
        help="only run the first N cases",
    )

    args = parser.parse_args(
        argv
    )

    database.initialize_database()

    demo = login_demo_user()

    if not demo.get("success"):

        print(
            "Could not load the demo account.",
            file=sys.stderr,
        )

        return 1

    user_id = demo["user"]["id"]

    rows = []

    for case in CASES[: args.limit]:

        result = run_case(
            user_id,
            case[0],
        )

        verdict = grade(
            case,
            result,
        )

        verdict.update(
            grade_answer(
                result["answer"],
                answer_checks(
                    case
                ),
            )
        )

        rows.append({
            **result,
            **verdict,
        })

        mark = "ok  " if verdict["matched"] else "MISS"

        if not verdict["answer_ok"]:

            mark = "WEAK"

        print(
            f'{mark} {result["seconds"]:>5.1f}s  '
            f'{str(verdict["first_tool"]):<28} {case[0]}'
        )

        for problem in verdict["answer_problems"]:

            print(
                f"       answer {problem}"
            )

    matched = sum(
        1
        for row in rows
        if row["matched"]
    )

    answered = sum(
        1
        for row in rows
        if row["answer_ok"]
    )

    seconds = [
        row["seconds"]
        for row in rows
    ]

    totals = {
        key: sum(
            row["usage"][key]
            for row in rows
        )
        for key in (
            "prompt",
            "completion",
            "reasoning",
            "steps",
        )
    }

    summary = {
        "cases": len(rows),
        "tool_selection_accuracy": round(
            matched / len(rows),
            3,
        ),
        "answer_accuracy": round(
            answered / len(rows),
            3,
        ),
        "mean_seconds": round(
            statistics.mean(seconds),
            2,
        ),
        "p95_seconds": round(
            sorted(seconds)[
                max(
                    0,
                    int(len(seconds) * 0.95) - 1,
                )
            ],
            2,
        ),
        **totals,
    }

    print()

    print(
        "summary: "
        f'{summary["cases"]} cases, '
        f'tool accuracy {summary["tool_selection_accuracy"]:.0%}, '
        f'answer accuracy {summary["answer_accuracy"]:.0%}, '
        f'mean {summary["mean_seconds"]}s, '
        f'p95 {summary["p95_seconds"]}s, '
        f'{totals["steps"]} LLM steps, '
        f'{totals["prompt"]} prompt + '
        f'{totals["completion"]} completion tokens '
        f'({totals["reasoning"]} reasoning)'
    )

    if args.json:

        Path(args.json).write_text(
            json.dumps(
                {
                    "summary": summary,
                    "results": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            f"written: {args.json}"
        )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
