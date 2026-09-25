"""List loans that are due soon or already overdue.

Run it from cron (or any scheduler) to drive reminders:

    python scripts/due_reminders.py --days 3
    python scripts/due_reminders.py --json

No mail transport is wired up on purpose: the script prints the list to
stdout so it can be piped into whatever the deployment already uses
(mail, webhook, log alerting) instead of hard-coding one provider.
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
import urllib.error
import urllib.request

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from agent.database import get_connection

from agent.tools import (
    calculate_fine_amount,
    parse_datetime,
)


def collect_due_loans(
    days=3,
    now=None,
):
    """Return one entry per active loan due within `days` or overdue."""

    now = now or datetime.now()

    horizon = (
        now
        +
        timedelta(
            days=days
        )
    )

    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                borrow_records.id,
                borrow_records.user_id,
                borrow_records.book_id,
                borrow_records.book_title,
                borrow_records.due_date,
                users.username,
                users.email

            FROM borrow_records

            LEFT JOIN users
                ON users.id = borrow_records.user_id

            WHERE borrow_records.returned_at IS NULL
            AND borrow_records.due_date IS NOT NULL

            ORDER BY borrow_records.due_date
            """
        ).fetchall()

    finally:

        connection.close()

    reminders = []

    for row in rows:

        due_datetime = parse_datetime(
            row["due_date"]
        )

        if due_datetime is None:

            continue

        if due_datetime > horizon:

            continue

        fine = calculate_fine_amount(
            row["due_date"],
            now,
        )

        reminders.append({

            "loan_id":
                row["id"],

            "user_id":
                row["user_id"],

            "username":
                row["username"],

            "email":
                row["email"],

            "book_id":
                row["book_id"],

            "title":
                row["book_title"],

            "due_date":
                row["due_date"],

            "is_overdue":
                fine["is_overdue"],

            "late_days":
                fine["late_days"],

            "fine_amount":
                fine["fine_amount"],

        })

    return reminders


# ============================================================
# DELIVERY
#
# Printing is the default. Delivery is opt-in because it needs
# credentials and a scheduler that the repository cannot know about.
# ============================================================

def smtp_settings():
    """Read SMTP configuration from the environment.

    Returns None when SMTP_HOST is missing, so the caller can report a
    clear error instead of failing once per recipient.
    """

    host = os.getenv("SMTP_HOST")

    if not host:

        return None

    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER"),
        "password": os.getenv("SMTP_PASSWORD"),
        "sender": (
            os.getenv("SMTP_FROM")
            or os.getenv("SMTP_USER")
        ),
        "use_tls": (
            os.getenv("SMTP_TLS", "1").lower()
            not in ("0", "false", "no", "off")
        ),
    }


def group_by_user(reminders):
    """One digest per reader, keyed by user id."""

    grouped = {}

    for item in reminders:

        grouped.setdefault(
            item["user_id"],
            [],
        ).append(item)

    return grouped


def build_digest(entries):
    """Return (subject, body) for one reader."""

    lines = []

    for item in entries:

        if item["is_overdue"]:

            lines.append(
                f'- {item["title"]} (book {item["book_id"]}): '
                f'due {item["due_date"]}, '
                f'overdue by {item["late_days"]} day(s), '
                f'fine {item["fine_amount"]:.2f}'
            )

        else:

            lines.append(
                f'- {item["title"]} (book {item["book_id"]}): '
                f'due {item["due_date"]}'
            )

    overdue_count = sum(
        1
        for item in entries
        if item["is_overdue"]
    )

    subject = "Library reminder: " + (
        f"{overdue_count} overdue item(s)"
        if overdue_count
        else f"{len(entries)} item(s) due soon"
    )

    body = (
        "Your library account has items that need attention:"
        "\n\n"
        + "\n".join(lines)
        + "\n\nReturn or renew them in the app to stop further fines.\n"
    )

    return subject, body


def send_digests(
    reminders,
    settings,
    smtp_factory=None,
):
    """Send one message per reader. Returns counts plus failures."""

    smtp_factory = smtp_factory or smtplib.SMTP

    sent = 0

    skipped = 0

    failures = []

    for entries in group_by_user(
        reminders
    ).values():

        recipient = entries[0].get(
            "email"
        )

        if not recipient:

            skipped += 1

            continue

        subject, body = build_digest(
            entries
        )

        message = EmailMessage()

        message["Subject"] = subject

        message["From"] = settings["sender"]

        message["To"] = recipient

        message.set_content(body)

        try:

            with smtp_factory(
                settings["host"],
                settings["port"],
                timeout=15,
            ) as client:

                if settings["use_tls"]:

                    client.starttls()

                if settings["user"]:

                    client.login(
                        settings["user"],
                        settings["password"],
                    )

                client.send_message(
                    message
                )

            sent += 1

        except Exception as error:

            failures.append(
                f"{recipient}: {error}"
            )

    return {
        "sent": sent,
        "skipped": skipped,
        "failures": failures,
    }


def post_webhook(
    url,
    reminders,
    opener=None,
):
    """POST the reminder list to a webhook (Slack, Feishu, custom)."""

    opener = opener or urllib.request.urlopen

    payload = json.dumps(
        {
            "type": "due_reminders",
            "count": len(reminders),
            "reminders": reminders,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:

        with opener(request, timeout=15) as response:

            return {
                "success": True,
                "status": getattr(
                    response,
                    "status",
                    None,
                ),
            }

    except Exception as error:

        return {
            "success": False,
            "message": str(error),
        }


def main(argv=None):

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help=(
            "how many days ahead counts "
            "as due soon (default: 3)"
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable output",
    )

    parser.add_argument(
        "--email",
        action="store_true",
        help=(
            "send one digest per reader "
            "(needs SMTP_HOST and friends)"
        ),
    )

    parser.add_argument(
        "--webhook",
        metavar="URL",
        help="POST the reminder list to a webhook",
    )

    args = parser.parse_args(
        argv
    )

    reminders = collect_due_loans(
        args.days
    )

    exit_code = 0

    if args.webhook:

        result = post_webhook(
            args.webhook,
            reminders,
        )

        if result["success"]:

            print(
                f"Webhook: sent {len(reminders)} reminder(s)."
            )

        else:

            print(
                f'Webhook failed: {result["message"]}',
                file=sys.stderr,
            )

            exit_code = 1

    if args.email:

        settings = smtp_settings()

        if settings is None:

            print(
                "Email delivery needs SMTP_HOST "
                "(plus SMTP_PORT / SMTP_USER / "
                "SMTP_PASSWORD / SMTP_FROM as required).",
                file=sys.stderr,
            )

            return 1

        report = send_digests(
            reminders,
            settings,
        )

        print(
            f'Email: {report["sent"]} sent, '
            f'{report["skipped"]} skipped (no address), '
            f'{len(report["failures"])} failed.'
        )

        for failure in report["failures"]:

            print(
                f"  {failure}",
                file=sys.stderr,
            )

        if report["failures"]:

            exit_code = 1

    if args.json:

        print(
            json.dumps(
                reminders,
                ensure_ascii=False,
                indent=2,
            )
        )

        return exit_code

    if not reminders:

        print(
            f"No loans due within {args.days} day(s)."
        )

        return exit_code

    for item in reminders:

        status = (
            "OVERDUE"
            if item["is_overdue"]
            else "due soon"
        )

        print(
            f'{item["due_date"]}  {status:9}'
            f'  {item["username"]}: {item["title"]}'
            f'  (book {item["book_id"]})'
        )

    return exit_code


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
