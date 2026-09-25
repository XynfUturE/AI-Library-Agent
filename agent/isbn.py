"""Look book metadata up by ISBN.

OpenLibrary only, standard library only: a cataloguing helper that runs
on an admin action does not justify another dependency.

Two requests per lookup, because an edition record stores authors as
key references:

    /isbn/<isbn>.json       -> title, publisher, date, author key
    /authors/<key>.json     -> the author name

The author call is best effort: a missing name must not fail the whole
lookup, because the admin can still type it.
"""

import json
import urllib.error
import urllib.request


OPENLIBRARY_BASE = "https://openlibrary.org"

COVERS_BASE = "https://covers.openlibrary.org/b/isbn"

REQUEST_TIMEOUT_SECONDS = 10


def normalize_isbn(isbn):
    """Return the bare ISBN-10/13 digits, or None if it is not an ISBN."""

    if not isinstance(isbn, str):

        return None

    cleaned = "".join(
        character
        for character in isbn
        if character.isalnum()
    ).upper()

    if len(cleaned) == 10:

        if (
            cleaned[:9].isdigit()
            and
            cleaned[9] in "0123456789X"
        ):

            return cleaned

        return None

    if len(cleaned) == 13 and cleaned.isdigit():

        return cleaned

    return None


def build_lookup_url(isbn):

    return f"{OPENLIBRARY_BASE}/isbn/{isbn}.json"


def build_author_url(author_key):
    """Turn an author reference ("/authors/OL34184A") into a URL."""

    if (
        not isinstance(author_key, str)
        or
        not author_key.startswith("/")
    ):

        return None

    return OPENLIBRARY_BASE + author_key + ".json"


def cover_url_for_isbn(isbn):

    return f"{COVERS_BASE}/{isbn}-L.jpg"


def parse_openlibrary_payload(isbn, payload, author_name=""):
    """Convert an edition record into library catalog fields."""

    if not isinstance(payload, dict) or not payload.get("title"):

        return None

    publishers = [
        name
        for name in payload.get("publishers") or []
        if name
    ]

    return {
        "isbn": isbn,
        "title": payload.get("title") or "",
        "author": author_name,
        "publisher": ", ".join(publishers),
        "pub_date": payload.get("publish_date") or "",
        "cover_url": cover_url_for_isbn(isbn),
    }


def fetch_json(url, opener):
    """GET one JSON document. Returns (payload, error_message)."""

    try:

        with opener(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:

            return (
                json.loads(
                    response.read().decode("utf-8")
                ),
                None,
            )

    except urllib.error.HTTPError as error:

        if error.code == 404:

            return None, "No book found for this ISBN."

        return None, (
            "The book service rejected the request "
            f"(HTTP {error.code})."
        )

    except (urllib.error.URLError, TimeoutError):

        return None, "The book service could not be reached."

    except (ValueError, UnicodeDecodeError):

        return None, "The book service returned an unreadable answer."


def fetch_author_name(payload, opener):
    """Resolve the first author reference. Failure returns ""."""

    authors = payload.get("authors") or []

    if not authors:

        return ""

    first = authors[0]

    url = build_author_url(
        first.get("key")
        if isinstance(first, dict)
        else None
    )

    if url is None:

        return ""

    author_payload, _error = fetch_json(
        url,
        opener,
    )

    if not isinstance(author_payload, dict):

        return ""

    return author_payload.get("name") or ""


def fetch_book_metadata(isbn, opener=None):
    """Look one ISBN up. Returns a catalog-shaped result dict."""

    cleaned = normalize_isbn(
        isbn
    )

    if cleaned is None:

        return {
            "success": False,
            "message": "Enter a valid ISBN-10 or ISBN-13.",
        }

    opener = opener or urllib.request.urlopen

    payload, error = fetch_json(
        build_lookup_url(cleaned),
        opener,
    )

    if error:

        return {
            "success": False,
            "message": error,
        }

    book = parse_openlibrary_payload(
        cleaned,
        payload,
        fetch_author_name(payload, opener),
    )

    if book is None:

        return {
            "success": False,
            "message": "No book found for this ISBN.",
        }

    return {
        "success": True,
        "message": "Book metadata found.",
        "book": book,
    }
