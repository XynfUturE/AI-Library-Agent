"""Look book metadata up by ISBN from the command line.

    python scripts/isbn_lookup.py 9780140328721

Prints the catalog fields to paste into the admin form or a CSV import.
"""

import argparse
import json
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from agent.isbn import fetch_book_metadata


def main(argv=None):

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "isbn",
        help="ISBN-10 or ISBN-13, dashes allowed",
    )

    parser.add_argument(
        "--csv",
        action="store_true",
        help="print one CSV line for the import form",
    )

    args = parser.parse_args(
        argv
    )

    result = fetch_book_metadata(
        args.isbn
    )

    if not result["success"]:

        print(
            result["message"],
            file=sys.stderr,
        )

        return 1

    book = result["book"]

    if args.csv:

        columns = (
            "title",
            "author",
            "isbn",
            "publisher",
            "pub_date",
            "cover_url",
        )

        print(
            ",".join(
                '"' + str(book.get(column, "")).replace('"', '""') + '"'
                for column in columns
            )
        )

        return 0

    print(
        json.dumps(
            book,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
