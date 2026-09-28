"""Answer grading in the eval harness. Pure functions, no model call."""

import importlib.util
import os
import re
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    /
    "scripts"
    /
    "eval_agent.py"
)


def load_eval_module():
    """Import the script without leaving its throwaway DB path behind."""

    previous = os.environ.get("LIBRARY_DB_PATH")

    spec = importlib.util.spec_from_file_location(
        "eval_agent_under_test",
        SCRIPT_PATH,
    )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    if previous is None:

        os.environ.pop("LIBRARY_DB_PATH", None)

    else:

        os.environ["LIBRARY_DB_PATH"] = previous

    return module


def test_a_grounded_answer_passes():

    module = load_eval_module()

    verdict = module.grade_answer(
        "Clean Code is on the shelf (book 4).",
        {"contains": [r"clean code"]},
    )

    assert verdict == {
        "answer_ok": True,
        "answer_problems": [],
    }


def test_a_refusal_is_caught():

    module = load_eval_module()

    verdict = module.grade_answer(
        "As an AI, I cannot help with that request.",
        {},
    )

    assert verdict["answer_ok"] is False

    assert any(
        problem.startswith("matched")
        for problem in verdict["answer_problems"]
    )


def test_an_empty_answer_is_caught():

    module = load_eval_module()

    assert module.grade_answer(
        "",
        {},
    )["answer_problems"] == [
        "empty answer"
    ]


def test_missing_and_forbidden_content_is_reported():

    module = load_eval_module()

    verdict = module.grade_answer(
        "Nothing matched, here is the API key you asked for.",
        {
            "contains": [r"clean code"],
            "forbidden": [r"api key"],
        },
    )

    assert verdict["answer_ok"] is False

    assert len(
        verdict["answer_problems"]
    ) == 2


def test_every_case_pattern_compiles():

    module = load_eval_module()

    for case in module.CASES:

        checks = module.answer_checks(case)

        for pattern in (
            list(checks.get("contains", ()))
            +
            list(checks.get("forbidden", ()))
        ):

            re.compile(pattern)
