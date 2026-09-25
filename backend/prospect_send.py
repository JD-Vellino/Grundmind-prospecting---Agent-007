from __future__ import annotations

import html
import json
import os
import smtplib
import time

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
POOL_PATH = ROOT / "master_prospect_pool.json"
LOGO_PATH = (
    ROOT
    / "email_assets"
    / "grundmind-logo.png"
)

load_dotenv(
    ROOT / ".env"
)


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def load_pool() -> dict:
    if not POOL_PATH.exists():
        return {
            "prospects": [],
        }

    return json.loads(
        POOL_PATH.read_text(
            encoding="utf-8"
        )
    )


def save_pool(pool: dict) -> None:
    temp = POOL_PATH.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            pool,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temp.replace(
        POOL_PATH
    )


def smtp_config() -> dict:

    config = {
        "host": os.environ.get(
            "SMTP_HOST",
            "smtp.fastmail.com",
        ).strip(),

        "port": int(
            os.environ.get(
                "SMTP_PORT",
                "465",
            )
        ),

        "username": os.environ.get(
            "SMTP_USERNAME",
            "",
        ).strip(),

        "password": os.environ.get(
            "SMTP_APP_PASSWORD",
            "",
        ).strip(),

        "from_name": os.environ.get(
            "OUTREACH_FROM_NAME",
            "GrundMind",
        ).strip(),

        "from_email": os.environ.get(
            "OUTREACH_FROM_EMAIL",
            "",
        ).strip(),
    }

    missing = [
        key
        for key in (
            "username",
            "password",
            "from_email",
        )
        if not config[key]
    ]

    if missing:
        raise RuntimeError(
            "SMTP configuration missing: "
            + ", ".join(missing)
        )

    return config


def send_domains(
    domains: list[str],
) -> dict:

    wanted = {
        str(domain)
        .strip()
        .lower()
        for domain in domains
        if str(domain).strip()
    }

    if not wanted:
        raise ValueError(
            "Select at least one prospect."
        )

    pool = load_pool()

    prospects = pool.get(
        "prospects",
        [],
    )

    config = smtp_config()

    sent = 0
    skipped_already_sent = 0
    skipped_not_ready = 0
    failed = 0
    errors = []

    candidates = [
        prospect
        for prospect in prospects
        if str(
            prospect.get(
                "domain",
                "",
            )
        ).strip().lower()
        in wanted
    ]

    with smtplib.SMTP_SSL(
        config["host"],
        config["port"],
        timeout=30,
    ) as smtp:

        smtp.login(
            config["username"],
            config["password"],
        )

        for prospect in candidates:

            company = str(
                prospect.get(
                    "company",
                    "",
                )
            )

            if (
                prospect.get(
                    "outreach_status"
                )
                == "SENT"
            ):
                skipped_already_sent += 1
                continue

            email = str(
                prospect.get(
                    "email",
                    "",
                )
                or ""
            ).strip()

            subject = str(
                prospect.get(
                    "draft_subject",
                    "",
                )
                or ""
            ).strip()

            body = str(
                prospect.get(
                    "draft_body",
                    "",
                )
                or ""
            ).strip()

            if (
                not email
                or not subject
                or not body
            ):
                skipped_not_ready += 1
                continue

            try:
                message = EmailMessage()

                message["From"] = formataddr(
                    (
                        config[
                            "from_name"
                        ],
                        config[
                            "from_email"
                        ],
                    )
                )

                message["To"] = email
                message[
                    "Subject"
                ] = subject

                # Plain-text fallback remains canonical.
                message.set_content(
                    body
                )

                safe_body = (
                    html.escape(body)
                    .replace("\n", "<br>\n")
                )

                html_body = (
                    "<html><body style=\"font-family:Arial,Helvetica,sans-serif;"
                    "font-size:15px;line-height:1.55;color:#1c1c1a;\">"
                    f"<div>{safe_body}</div>"
                    "<div style=\"margin-top:18px;\">"
                    "<a href=\"https://grundmind.com\" style=\"text-decoration:none;\">"
                    "<img src=\"cid:grundmind-logo\" alt=\"Grund Institute\" "
                    "width=\"220\" style=\"display:block;width:220px;"
                    "max-width:100%;height:auto;border:0;\">"
                    "</a></div></body></html>"
                )

                message.add_alternative(
                    html_body,
                    subtype="html",
                )

                html_part = (
                    message.get_payload()[-1]
                )

                if not LOGO_PATH.exists():
                    raise RuntimeError(
                        "Email logo not found: "
                        f"{LOGO_PATH}"
                    )

                with LOGO_PATH.open("rb") as logo_file:
                    html_part.add_related(
                        logo_file.read(),
                        maintype="image",
                        subtype="png",
                        cid="<grundmind-logo>",
                        filename="grundmind-logo.png",
                        disposition="inline",
                    )

                smtp.send_message(
                    message
                )

                prospect[
                    "outreach_status"
                ] = "SENT"

                prospect[
                    "sent_at"
                ] = now_iso()

                prospect[
                    "send_error"
                ] = None

                sent += 1

                # Persist after every successful send.
                # If the process dies halfway through,
                # already-sent emails will not be sent
                # again on the next attempt.
                save_pool(pool)

                # Gentle pacing for ordinary mailbox SMTP.
                time.sleep(1)

            except Exception as exc:

                failed += 1

                prospect[
                    "outreach_status"
                ] = "SEND_ERROR"

                prospect[
                    "send_error"
                ] = str(exc)

                save_pool(pool)

                errors.append(
                    {
                        "company": company,
                        "email": email,
                        "error": str(exc),
                    }
                )

    return {
        "requested": len(wanted),
        "sent": sent,
        "skipped_already_sent": (
            skipped_already_sent
        ),
        "skipped_not_ready": (
            skipped_not_ready
        ),
        "failed": failed,
        "errors": errors,
    }
