"""Reminder delivery: digest building, SMTP, webhook."""

import json

from scripts.due_reminders import (
    build_digest,
    group_by_user,
    post_webhook,
    send_digests,
    smtp_settings,
)


def entry(
    user_id=1,
    email="reader@example.com",
    is_overdue=False,
):

    return {
        "loan_id": user_id * 10,
        "user_id": user_id,
        "username": f"reader{user_id}",
        "email": email,
        "book_id": 7,
        "title": "Clean Code",
        "due_date": "2026-01-20 10:00:00",
        "is_overdue": is_overdue,
        "late_days": 2 if is_overdue else 0,
        "fine_amount": 1.0 if is_overdue else 0.0,
    }


def settings(**overrides):

    values = {
        "host": "smtp.example.com",
        "port": 587,
        "user": None,
        "password": None,
        "sender": "library@example.com",
        "use_tls": False,
    }

    values.update(
        overrides
    )

    return values


class FakeSMTP:

    instances = []

    def __init__(
        self,
        host,
        port,
        timeout=None,
    ):

        self.host = host
        self.port = port
        self.messages = []
        self.tls_started = False
        self.login_arguments = None
        FakeSMTP.instances.append(self)

    def __enter__(self):

        return self

    def __exit__(
        self,
        *arguments,
    ):

        return False

    def starttls(self):

        self.tls_started = True

    def login(
        self,
        user,
        password,
    ):

        self.login_arguments = (user, password)

    def send_message(
        self,
        message,
    ):

        self.messages.append(message)


def test_entries_group_per_reader():

    grouped = group_by_user([
        entry(user_id=1),
        entry(user_id=1),
        entry(user_id=2, email=None),
    ])

    assert sorted(grouped) == [1, 2]
    assert len(grouped[1]) == 2


def test_digest_mentions_overdue_state():

    subject, body = build_digest([
        entry(is_overdue=True),
    ])

    assert "overdue" in subject
    assert "Clean Code" in body
    assert "fine 1.00" in body


def test_digest_for_due_soon_items():

    subject, body = build_digest([
        entry(),
    ])

    assert "due soon" in subject
    assert "2026-01-20 10:00:00" in body


def test_each_reader_gets_one_message():

    FakeSMTP.instances.clear()

    report = send_digests(
        [
            entry(user_id=1),
            entry(user_id=1),
            entry(user_id=2),
        ],
        settings(),
        smtp_factory=FakeSMTP,
    )

    assert report == {
        "sent": 2,
        "skipped": 0,
        "failures": [],
    }

    assert len(FakeSMTP.instances) == 2

    assert all(
        len(client.messages) == 1
        for client in FakeSMTP.instances
    )


def test_reader_without_address_is_skipped():

    report = send_digests(
        [
            entry(email=None),
        ],
        settings(),
        smtp_factory=FakeSMTP,
    )

    assert report["sent"] == 0
    assert report["skipped"] == 1


def test_smtp_failure_is_reported_not_raised():

    class BrokenSMTP(FakeSMTP):

        def send_message(
            self,
            message,
        ):

            raise RuntimeError("mailbox unavailable")

    report = send_digests(
        [
            entry(),
        ],
        settings(),
        smtp_factory=BrokenSMTP,
    )

    assert report["sent"] == 0
    assert report["failures"]
    assert "mailbox unavailable" in report["failures"][0]


def test_tls_and_login_follow_the_settings():

    FakeSMTP.instances.clear()

    send_digests(
        [
            entry(),
        ],
        settings(
            user="bot",
            password="secret",
            use_tls=True,
        ),
        smtp_factory=FakeSMTP,
    )

    client = FakeSMTP.instances[0]

    assert client.tls_started is True
    assert client.login_arguments == ("bot", "secret")


def test_smtp_settings_need_a_host(monkeypatch):

    monkeypatch.delenv("SMTP_HOST", raising=False)

    assert smtp_settings() is None

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "bot")
    monkeypatch.setenv("SMTP_FROM", "library@example.com")

    configured = smtp_settings()

    assert configured["port"] == 2525
    assert configured["sender"] == "library@example.com"
    assert configured["use_tls"] is True


def test_webhook_posts_the_reminders():

    captured = {}

    class FakeWebhookResponse:

        status = 204

        def __enter__(self):

            return self

        def __exit__(
            self,
            *arguments,
        ):

            return False

    def opener(request, timeout=None):

        captured["url"] = request.full_url
        captured["body"] = json.loads(
            request.data.decode("utf-8")
        )
        captured["method"] = request.get_method()

        return FakeWebhookResponse()

    result = post_webhook(
        "https://hooks.example.com/library",
        [entry()],
        opener=opener,
    )

    assert result["success"] is True
    assert captured["url"] == "https://hooks.example.com/library"
    assert captured["method"] == "POST"
    assert captured["body"]["count"] == 1
    assert captured["body"]["reminders"][0]["title"] == "Clean Code"


def test_webhook_failure_is_returned():

    def opener(request, timeout=None):

        raise OSError("connection refused")

    result = post_webhook(
        "https://hooks.example.com/library",
        [entry()],
        opener=opener,
    )

    assert result["success"] is False
    assert "connection refused" in result["message"]
