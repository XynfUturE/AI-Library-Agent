"""ISBN lookup: validation, parsing, author resolution, failures."""

import json
import urllib.error

from agent import isbn


EDITION_PAYLOAD = {
    "title": "Fantastic Mr. Fox",
    "publishers": ["Puffin"],
    "publish_date": "October 1, 1988",
    "covers": [15152634],
    "authors": [
        {"key": "/authors/OL34184A"},
    ],
}

AUTHOR_PAYLOAD = {
    "name": "Roald Dahl",
}


class FakeResponse:

    def __init__(
        self,
        payload,
        status=200,
    ):

        self._payload = payload

        self.status = status

    def read(self):

        return json.dumps(
            self._payload
        ).encode("utf-8")

    def __enter__(self):

        return self

    def __exit__(
        self,
        *arguments,
    ):

        return False


def library_opener(
    edition=EDITION_PAYLOAD,
    author=AUTHOR_PAYLOAD,
):
    """Fake OpenLibrary: answers by URL and records the requests."""

    requested = []

    def opener(url, timeout=None):

        requested.append(url)

        if "/authors/" in url:

            if isinstance(author, Exception):

                raise author

            return FakeResponse(author)

        if isinstance(edition, Exception):

            raise edition

        return FakeResponse(edition)

    opener.requested = requested

    return opener


def test_normalize_accepts_common_shapes():

    assert isbn.normalize_isbn(
        "978-0-14-032872-1"
    ) == "9780140328721"

    assert isbn.normalize_isbn(
        "0-306-40615-2"
    ) == "0306406152"

    assert isbn.normalize_isbn(
        "080442957x"
    ) == "080442957X"


def test_normalize_rejects_junk():

    assert isbn.normalize_isbn("123") is None
    assert isbn.normalize_isbn("") is None
    assert isbn.normalize_isbn(None) is None
    assert isbn.normalize_isbn("abcdefghij") is None


def test_lookup_url_targets_the_edition_endpoint():

    assert isbn.build_lookup_url(
        "9780140328721"
    ) == (
        "https://openlibrary.org/isbn/"
        "9780140328721.json"
    )


def test_author_url_is_only_built_for_real_keys():

    assert isbn.build_author_url(
        "/authors/OL34184A"
    ) == "https://openlibrary.org/authors/OL34184A.json"

    assert isbn.build_author_url(None) is None

    assert isbn.build_author_url("OL34184A") is None

    assert isbn.build_author_url(
        "https://evil.example/authors"
    ) is None


def test_fetch_maps_the_edition_and_author():

    opener = library_opener()

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is True, result

    book = result["book"]

    assert book["title"] == "Fantastic Mr. Fox"
    assert book["author"] == "Roald Dahl"
    assert book["publisher"] == "Puffin"
    assert book["pub_date"] == "October 1, 1988"

    assert book["cover_url"] == (
        "https://covers.openlibrary.org/b/isbn/"
        "9780140328721-L.jpg"
    )

    assert len(opener.requested) == 2


def test_missing_author_skips_the_second_request():

    opener = library_opener(
        edition={
            "title": "Anonymous Work",
            "publishers": [],
        }
    )

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is True, result
    assert result["book"]["author"] == ""
    assert len(opener.requested) == 1


def test_author_failure_still_returns_the_book():

    opener = library_opener(
        author=urllib.error.URLError("offline")
    )

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is True, result
    assert result["book"]["author"] == ""
    assert result["book"]["title"] == "Fantastic Mr. Fox"


def test_unknown_isbn_reports_not_found():

    opener = library_opener(
        edition=urllib.error.HTTPError(
            "https://openlibrary.org/isbn/x.json",
            404,
            "Not Found",
            {},
            None,
        )
    )

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is False
    assert "No book found" in result["message"]


def test_server_error_is_reported_with_its_code():

    opener = library_opener(
        edition=urllib.error.HTTPError(
            "https://openlibrary.org/isbn/x.json",
            503,
            "Service Unavailable",
            {},
            None,
        )
    )

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is False
    assert "503" in result["message"]


def test_network_failure_is_reported():

    opener = library_opener(
        edition=urllib.error.URLError("offline")
    )

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is False
    assert "could not be reached" in result["message"]


def test_bad_isbn_never_touches_the_network():

    def opener(url, timeout=None):

        raise AssertionError(
            "the network must not be called"
        )

    result = isbn.fetch_book_metadata(
        "not-an-isbn",
        opener=opener,
    )

    assert result["success"] is False
    assert "valid ISBN" in result["message"]


def test_garbage_response_is_reported():

    class GarbageResponse(FakeResponse):

        def read(self):

            return b"<html>not json</html>"

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=lambda url, timeout=None: GarbageResponse({}),
    )

    assert result["success"] is False
    assert "unreadable" in result["message"]


def test_payload_without_a_title_is_not_a_book():

    opener = library_opener(
        edition={
            "publishers": ["Nobody"],
        }
    )

    result = isbn.fetch_book_metadata(
        "9780140328721",
        opener=opener,
    )

    assert result["success"] is False
