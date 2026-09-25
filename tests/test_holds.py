"""Demand queue: holds, purchase suggestions, promotion on return."""

import uuid
from datetime import datetime

from agent import analytics
from agent.auth import register_user
from agent.tools import (
    borrow_book,
    cancel_hold,
    get_my_holds,
    request_book,
    return_book,
)


def make_reader():

    result = register_user(
        "queuer_" + uuid.uuid4().hex[:8],
        "Passw0rd!23",
        "Queue Reader",
    )

    assert result["success"] is True, result

    return result["user"]


def test_available_book_is_not_queued(
    app_database,
    new_user,
    available_book,
):

    result = request_book(
        new_user["id"],
        available_book["id"],
    )

    assert result["success"] is True, result
    assert result["kind"] == "available"
    assert get_my_holds(new_user["id"]) == []


def test_lent_out_book_joins_the_queue(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    reader = make_reader()

    result = request_book(
        reader["id"],
        available_book["id"],
    )

    assert result["success"] is True, result
    assert result["kind"] == "hold"
    assert result["queue_position"] == 1

    holds = get_my_holds(reader["id"])

    assert len(holds) == 1
    assert holds[0]["status"] == "waiting"
    assert holds[0]["queue_position"] == 1


def test_hold_timestamps_use_local_time(
    app_database,
    new_user,
):
    """Regression: created_at used to be UTC while loans are local."""

    title = "Timestamp Check " + uuid.uuid4().hex[:6]

    result = request_book(
        new_user["id"],
        title=title,
    )

    assert result["success"] is True, result

    created_at = get_my_holds(
        new_user["id"]
    )[0]["created_at"]

    stamped = datetime.strptime(
        created_at,
        "%Y-%m-%d %H:%M:%S",
    )

    drift = abs(
        (
            datetime.now()
            -
            stamped
        ).total_seconds()
    )

    assert drift < 60, created_at


def test_second_reader_waits_behind_the_first(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    first = request_book(
        make_reader()["id"],
        available_book["id"],
    )

    second = request_book(
        make_reader()["id"],
        available_book["id"],
    )

    assert first["queue_position"] == 1
    assert second["queue_position"] == 2
    assert second["estimated_wait_days"] >= 14


def test_repeat_request_is_not_queued_twice(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    reader = make_reader()

    first = request_book(
        reader["id"],
        available_book["id"],
    )

    again = request_book(
        reader["id"],
        available_book["id"],
    )

    assert again["duplicate"] is True
    assert again["hold_id"] == first["hold_id"]
    assert len(get_my_holds(reader["id"])) == 1


def test_holder_of_the_loan_is_told_to_keep_it(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    result = request_book(
        new_user["id"],
        available_book["id"],
    )

    assert result["kind"] == "already_borrowed"


def test_return_promotes_the_next_reader(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    reader = make_reader()

    hold = request_book(
        reader["id"],
        available_book["id"],
    )

    returned = return_book(
        available_book["id"],
        new_user["id"],
    )

    assert returned["success"] is True, returned
    assert returned["next_in_queue"]["hold_id"] == hold["hold_id"]
    assert returned["next_in_queue"]["user_id"] == reader["id"]

    promoted = get_my_holds(reader["id"])

    assert promoted[0]["status"] == "ready"
    assert promoted[0]["ready_at"]


def test_return_without_a_queue_reports_nobody(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    returned = return_book(
        available_book["id"],
        new_user["id"],
    )

    assert returned["next_in_queue"] is None


def test_unknown_title_becomes_a_purchase_suggestion(
    app_database,
    new_user,
):

    title = "Nobody Owns This " + uuid.uuid4().hex[:6]

    result = request_book(
        new_user["id"],
        title=title,
    )

    assert result["success"] is True, result
    assert result["kind"] == "suggestion"
    assert result["duplicate"] is False

    holds = get_my_holds(new_user["id"])

    assert holds[0]["kind"] == "suggestion"
    assert "queue_position" not in holds[0]

    again = request_book(
        new_user["id"],
        title=title.upper(),
    )

    assert again["duplicate"] is True


def test_request_needs_an_id_or_a_title(
    app_database,
    new_user,
):

    result = request_book(
        new_user["id"]
    )

    assert result["success"] is False


def test_unknown_book_id_is_reported(
    app_database,
    new_user,
):

    result = request_book(
        new_user["id"],
        999999,
    )

    assert result["success"] is False
    assert "not found" in result["message"]


def test_reader_can_withdraw_their_request(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    reader = make_reader()

    hold = request_book(
        reader["id"],
        available_book["id"],
    )

    withdrawn = cancel_hold(
        reader["id"],
        hold["hold_id"],
    )

    assert withdrawn["success"] is True, withdrawn
    assert get_my_holds(reader["id"]) == []

    twice = cancel_hold(
        reader["id"],
        hold["hold_id"],
    )

    assert twice["success"] is False


def test_another_reader_cannot_withdraw_the_request(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    reader = make_reader()

    hold = request_book(
        reader["id"],
        available_book["id"],
    )

    stolen = cancel_hold(
        new_user["id"],
        hold["hold_id"],
    )

    assert stolen["success"] is False
    assert len(get_my_holds(reader["id"])) == 1


def test_analytics_lists_pending_demand(
    app_database,
    new_user,
    available_book,
):

    assert borrow_book(
        available_book["id"],
        new_user["id"],
    )["success"] is True

    request_book(
        make_reader()["id"],
        available_book["id"],
    )

    title = "Wanted By Many " + uuid.uuid4().hex[:6]

    request_book(
        new_user["id"],
        title=title,
    )

    dashboard = analytics.get_dashboard()

    assert dashboard["overview"]["pending_hold_count"] >= 1
    assert dashboard["overview"]["pending_suggestion_count"] >= 1

    titles = [
        entry["title"]
        for entry in dashboard["purchase_suggestions"]
    ]

    assert title in titles
