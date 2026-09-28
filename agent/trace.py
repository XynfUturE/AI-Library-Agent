"""Per-turn agent tracing.

One JSON object per line, covering the steps that cost money or
explain a wrong answer: every LLM call (tokens, cache split, latency)
and every tool call (name, arguments, outcome, latency).

Tracing is off unless AGENT_TRACE_PATH is set, and the same records
are emitted on the "library_agent.trace" logger, so a host can ship
them with normal structured logging instead of reading the file.
"""

import json
import logging
import os
import time


TRACE_PATH_ENV = "AGENT_TRACE_PATH"

logger = logging.getLogger(
    "library_agent.trace"
)


def record(
    event,
    **fields,
):
    """
    Write one structured trace record.

    Returns the record so a caller can assert on it in tests.
    """

    payload = {
        "ts": round(
            time.time(),
            3,
        ),
        "event": event,
    }

    payload.update(
        fields
    )

    line = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )

    logger.info(
        line
    )

    path = os.getenv(
        TRACE_PATH_ENV
    )

    if not path:

        return payload

    # ponytail: one open/append per record. Batch the writes if a
    # trace ever becomes hot enough that this shows up in a profile.
    with open(
        path,
        "a",
        encoding="utf-8",
    ) as handle:

        handle.write(
            line
            +
            "\n"
        )

    return payload
