"""Paging on the list endpoints, and the count that goes with it."""

import pytest

from agent import catalog

from test_web_api import (
    client,
    log_in,
)


def test_count_catalog_matches_the_unpaged_list(app_database):

    everything = catalog.query_catalog()

    assert catalog.count_catalog() == len(everything)

    assert catalog.count_catalog(
        keyword="Clean"
    ) == len(
        catalog.query_catalog(
            keyword="Clean"
        )
    )


def test_catalog_pages_do_not_overlap(app_database):

    first = catalog.query_catalog(limit=3)

    second = catalog.query_catalog(
        limit=3,
        offset=3,
    )

    assert len(first) == 3

    assert len(second) == 3

    assert {
        book["id"]
        for book in first
    }.isdisjoint(
        {
            book["id"]
            for book in second
        }
    )


def test_an_unknown_category_counts_as_zero(app_database):

    assert catalog.count_catalog(
        category_id=99999
    ) == 0

    assert catalog.query_catalog(
        category_id=99999
    ) == []


def test_books_endpoint_returns_a_page_and_a_total(client):

    session_id = log_in(client)

    headers = {
        "X-Session-ID": session_id,
    }

    everything = client.get(
        "/api/books",
        headers=headers,
    ).json()

    page = client.get(
        "/api/books",
        params={
            "limit": 5,
            "offset": 5,
        },
        headers=headers,
    )

    assert page.status_code == 200, page.text

    body = page.json()

    assert len(body["items"]) == 5

    assert body["total"] == len(
        everything["items"]
    )

    assert body["limit"] == 5

    assert body["offset"] == 5

    assert body["items"] != everything["items"][
        :5
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 500},
        {"offset": -1},
        {"limit": "all"},
    ],
)
def test_a_bad_page_is_rejected(client, params):

    session_id = log_in(client)

    response = client.get(
        "/api/books",
        params=params,
        headers={
            "X-Session-ID": session_id,
        },
    )

    assert response.status_code == 422


def test_history_can_be_paged(client):

    session_id = log_in(client)

    headers = {
        "X-Session-ID": session_id,
    }

    unpaged = client.get(
        "/api/shelf/history",
        headers=headers,
    ).json()

    page = client.get(
        "/api/shelf/history",
        params={"limit": 1},
        headers=headers,
    ).json()

    assert page["total"] == len(
        unpaged["items"]
    )

    assert len(page["items"]) == min(
        1,
        page["total"],
    )
