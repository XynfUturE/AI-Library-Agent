from typing import Any

import secrets
import time


# Idle sessions (no authenticated request) are evicted after this window.
SESSION_IDLE_TIMEOUT = 60 * 60

# Hard upper bound on in-memory sessions to bound memory growth.
SESSION_HARD_LIMIT = 2000

_sessions: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _touch(session: dict[str, Any]) -> None:
    session["last_active"] = _now()


def _sweep_expired_sessions() -> None:
    now = _now()
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session.get("last_active", 0.0) > SESSION_IDLE_TIMEOUT
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)


def create_session(user_id: int) -> str:
    """Create a new in-memory session with idle-based expiry."""

    session_id = secrets.token_urlsafe(32)

    now = _now()
    _sessions[session_id] = {
        "user_id": int(user_id),
        "agent": None,
        "created_at": now,
        "last_active": now,
    }

    _sweep_expired_sessions()

    # Defensive cap: if a burst of logins overflows the hard limit,
    # evict the oldest sessions so memory stays bounded.
    while len(_sessions) > SESSION_HARD_LIMIT:
        oldest = min(_sessions.items(), key=lambda item: item[1].get("created_at", 0.0))
        _sessions.pop(oldest[0], None)

    return session_id


def get_session(session_id: str | None):
    """Get a session by session ID and refresh its idle timestamp."""

    if not session_id:
        return None

    session = _sessions.get(session_id)

    if session is not None:
        _touch(session)

    return session


def set_agent(session_id: str, agent) -> bool:
    """Attach an Agent instance to a session."""

    session = get_session(session_id)

    if session is None:
        return False

    session["agent"] = agent

    return True


def delete_session(session_id: str | None) -> None:
    """Delete an existing session."""

    if not session_id:
        return

    _sessions.pop(session_id, None)
