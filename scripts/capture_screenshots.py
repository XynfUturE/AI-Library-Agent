"""Capture README screenshots from a locally running server.

    pip install playwright
    python -m uvicorn web.app:app --port 8000
    python scripts/capture_screenshots.py

Uses a Chromium browser already installed on the machine (Edge or
Chrome), so no browser binaries are downloaded. It is deliberately not
in requirements-dev.txt: the test suite does not need it.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = PROJECT_ROOT / "docs" / "screenshots"

VIEWPORT = {
    "width": 1440,
    "height": 900,
}


def launch_installed_browser(playwright):
    """Use Edge or Chrome already on the machine, no download."""

    errors = []

    for channel in ("msedge", "chrome"):

        try:

            return playwright.chromium.launch(
                channel=channel
            )

        except Exception as error:

            errors.append(
                f"{channel}: {error}"
            )

    raise SystemExit(
        "No installed Chromium browser found.\n"
        + "\n".join(errors)
    )


def capture(base_url):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    written = []

    with sync_playwright() as playwright:

        browser = launch_installed_browser(
            playwright
        )

        page = browser.new_page(
            viewport=VIEWPORT
        )

        page.goto(
            base_url,
            wait_until="networkidle",
        )

        page.wait_for_timeout(600)

        written.append(
            shot(
                page,
                "01-login",
            )
        )

        page.click("#demo-login-button")

        page.wait_for_selector(
            "#sidebar",
            state="visible",
        )

        page.wait_for_timeout(900)

        written.append(
            shot(
                page,
                "02-chat",
            )
        )

        page.click('[data-route="shelf"]')

        page.wait_for_timeout(900)

        written.append(
            shot(
                page,
                "03-shelf",
            )
        )

        page.click('[data-route="catalog"]')

        page.wait_for_timeout(900)

        written.append(
            shot(
                page,
                "04-catalog",
            )
        )

        browser.close()

    return written


def shot(page, name):

    path = OUTPUT_DIR / f"{name}.png"

    page.screenshot(
        path=str(path)
    )

    return path


def main(argv=None):

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/",
    )

    args = parser.parse_args(
        argv
    )

    written = capture(
        args.base_url
    )

    for path in written:

        print(
            f"{path.relative_to(PROJECT_ROOT)} "
            f"({path.stat().st_size // 1024} KB)"
        )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
