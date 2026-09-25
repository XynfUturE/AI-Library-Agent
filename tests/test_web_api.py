"""HTTP surface: session guard, chat plumbing and the rate limit."""

import pytest

from fastapi.testclient import TestClient

from web import app as web_app


class FakeAgent:
    """Stands in for LibraryAgent so no LLM call is made."""

    def __init__(
        self,
        user_id,
    ):

        self.user_id = user_id

        self.messages = []

    def chat(
        self,
        message,
    ):

        return f"echo: {message}"

    def chat_stream(
        self,
        message,
    ):

        yield {
            "type": "agent_start",
            "message": "Thinking...",
        }

        yield {
            "type": "final",
            "message": f"echo: {message}",
        }


@pytest.fixture()
def client(
    app_database,
    monkeypatch,
):

    monkeypatch.setattr(
        web_app,
        "LibraryAgent",
        FakeAgent,
    )

    web_app._chat_hits.clear()

    with TestClient(
        web_app.app
    ) as test_client:

        yield test_client

    web_app._chat_hits.clear()


def log_in(client):

    response = client.post(
        "/api/demo-login"
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["success"] is True, body

    return body["session_id"]


def test_shelf_requires_a_session(client):

    assert (
        client.get(
            "/api/shelf/summary"
        ).status_code
        ==
        401
    )


def test_demo_login_then_chat(client):

    session_id = log_in(
        client
    )

    response = client.post(
        "/api/chat",
        json={
            "message": "hello",
        },
        headers={
            "X-Session-Id": session_id,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["reply"] == "echo: hello"


def test_shelf_summary_works_after_login(client):

    session_id = log_in(
        client
    )

    response = client.get(
        "/api/shelf/summary",
        headers={
            "X-Session-Id": session_id,
        },
    )

    assert response.status_code == 200, response.text


def test_chat_rate_limit_returns_429(
    client,
    monkeypatch,
):

    monkeypatch.setattr(
        web_app,
        "CHAT_RATE_LIMIT_PER_MINUTE",
        2,
    )

    session_id = log_in(
        client
    )

    headers = {
        "X-Session-Id": session_id,
    }

    for _ in range(2):

        allowed = client.post(
            "/api/chat",
            json={
                "message": "hi",
            },
            headers=headers,
        )

        assert allowed.status_code == 200, allowed.text

    blocked = client.post(
        "/api/chat",
        json={
            "message": "hi",
        },
        headers=headers,
    )

    assert blocked.status_code == 429, blocked.text


def test_admin_endpoints_reject_a_member(client):

    registered = client.post(
        "/api/register",
        json={
            "username": "member_only",
            "password": "Passw0rd!23",
        },
    )

    assert registered.status_code == 200, registered.text

    headers = {
        "X-Session-Id": registered.json()["session_id"],
    }

    analytics = client.get(
        "/api/admin/analytics",
        headers=headers,
    )

    lookup = client.post(
        "/api/admin/books/lookup-isbn",
        json={
            "isbn": "9780140328721",
        },
        headers=headers,
    )

    assert analytics.status_code == 403, analytics.text
    assert lookup.status_code == 403, lookup.text


def test_admin_analytics_returns_counters(client):

    session_id = log_in(
        client
    )

    response = client.get(
        "/api/admin/analytics",
        headers={
            "X-Session-Id": session_id,
        },
    )

    assert response.status_code == 200, response.text

    payload = response.json()

    assert payload["overview"]["title_count"] > 0
    assert "top_books" in payload
    assert "monthly_loans" in payload


def test_admin_isbn_lookup_returns_metadata(
    client,
    monkeypatch,
):

    monkeypatch.setattr(
        web_app.isbn_service,
        "fetch_book_metadata",
        lambda isbn: {
            "success": True,
            "message": "Book metadata found.",
            "book": {
                "isbn": isbn,
                "title": "Matilda",
            },
        },
    )

    session_id = log_in(
        client
    )

    response = client.post(
        "/api/admin/books/lookup-isbn",
        json={
            "isbn": "9780140328721",
        },
        headers={
            "X-Session-Id": session_id,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["book"]["title"] == "Matilda"
