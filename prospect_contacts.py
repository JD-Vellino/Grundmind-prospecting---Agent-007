from __future__ import annotations

import json
import os

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv(
    Path(__file__).resolve().with_name(".env")
)

POOL_PATH = Path("master_prospect_pool.json")
HUNTER_BASE = "https://api.hunter.io/v2"


TEAM_CONFIG = {
    "Operations": {
        "departments": "operations,management",
        "titles": (
            "Head of Operations,"
            "VP Operations,"
            "Operations Director,"
            "Transformation Director"
        ),
    },
    "Customer Experience": {
        "departments": "support,operations,management",
        "titles": (
            "Head of Customer Experience,"
            "VP Customer Experience,"
            "Customer Experience Director,"
            "Customer Service Director"
        ),
    },
    "Finance": {
        "departments": "finance,management",
        "titles": (
            "Head of Finance Transformation,"
            "VP Finance,"
            "Finance Director,"
            "CFO"
        ),
    },
    "Supply Chain": {
        "departments": "operations,management",
        "titles": (
            "Head of Supply Chain,"
            "VP Supply Chain,"
            "Supply Chain Director,"
            "Supply Chain Transformation"
        ),
    },
    "Marketing": {
        "departments": "marketing,management",
        "titles": (
            "Chief Marketing Officer,"
            "VP Marketing,"
            "Marketing Director"
        ),
    },
    "HR / People": {
        "departments": "hr,management",
        "titles": (
            "Chief People Officer,"
            "Chief Human Resources Officer,"
            "VP People,"
            "HR Director"
        ),
    },
    "IT / AI": {
        "departments": "it,executive,management",
        "titles": (
            "Chief AI Officer,"
            "Head of AI,"
            "Chief Digital Officer,"
            "Head of Digital Transformation,"
            "VP Digital Transformation"
        ),
    },
    "R&D": {
        "departments": "management,it,health",
        "titles": (
            "Head of R&D,"
            "VP R&D,"
            "R&D Director,"
            "Head of Innovation"
        ),
    },
    "Digital Transformation": {
        "departments": "executive,it,management",
        "titles": (
            "Chief Digital Officer,"
            "Head of Digital Transformation,"
            "VP Digital Transformation,"
            "Transformation Director,"
            "Head of AI"
        ),
    },
    "Innovation": {
        "departments": "executive,management,it",
        "titles": (
            "Chief Innovation Officer,"
            "Head of Innovation,"
            "VP Innovation,"
            "Innovation Director,"
            "Head of AI"
        ),
    },
}


DEFAULT_CONFIG = {
    "departments": "executive,management,it,operations",
    "titles": (
        "Chief Digital Officer,"
        "Head of Digital Transformation,"
        "VP Digital Transformation,"
        "Head of AI,"
        "Chief AI Officer,"
        "Transformation Director"
    ),
}


def load_pool() -> dict:
    if not POOL_PATH.exists():
        return {"prospects": []}

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

    temp.replace(POOL_PATH)


def hunter_get(
    path: str,
    params: dict,
) -> dict:

    api_key = os.environ.get(
        "HUNTER_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "HUNTER_API_KEY is not configured."
        )

    url = (
        HUNTER_BASE
        + path
        + "?"
        + urlencode(params)
    )

    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "X-API-KEY": api_key,
        },
    )

    try:
        with urlopen(
            request,
            timeout=60,
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Hunter returned HTTP "
            f"{exc.code}: {body[:700]}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            f"Hunter connection failed: "
            f"{exc.reason}"
        ) from exc


def domain_search(
    domain: str,
    params: dict,
) -> list[dict]:

    query = {
        "domain": domain,
        "limit": 10,
        "type": "personal",
        **params,
    }

    result = hunter_get(
        "/domain-search",
        query,
    )

    data = result.get(
        "data",
        {},
    )

    if not isinstance(data, dict):
        return []

    emails = data.get(
        "emails",
        [],
    )

    if not isinstance(
        emails,
        list,
    ):
        return []

    return [
        item
        for item in emails
        if isinstance(item, dict)
    ]


def find_people(
    domain: str,
    likely_team: str,
) -> list[dict]:

    config = TEAM_CONFIG.get(
        likely_team,
        DEFAULT_CONFIG,
    )

    searches = [
        # Best case: matching leadership title.
        {
            "job_titles": config[
                "titles"
            ],
            "seniority": (
                "executive,senior"
            ),
            "decision_maker": "true",
            "required_field": (
                "full_name,position"
            ),
            "verification_status": (
                "valid,accept_all"
            ),
        },

        # Broaden to likely department.
        {
            "department": config[
                "departments"
            ],
            "seniority": (
                "executive,senior"
            ),
            "decision_maker": "true",
            "required_field": (
                "full_name,position"
            ),
            "verification_status": (
                "valid,accept_all"
            ),
        },

        # Final broad leadership fallback.
        {
            "seniority": (
                "executive,senior"
            ),
            "decision_maker": "true",
            "required_field": (
                "full_name,position"
            ),
            "verification_status": (
                "valid,accept_all"
            ),
        },
    ]

    for search in searches:

        people = domain_search(
            domain,
            search,
        )

        if people:
            return people

    return []


def person_score(
    person: dict,
    likely_team: str,
) -> tuple:

    seniority = str(
        person.get(
            "seniority",
            "",
        )
    ).lower()

    verification = (
        person.get(
            "verification"
        )
        or {}
    )

    verification_status = str(
        verification.get(
            "status",
            "",
        )
    ).lower()

    confidence = int(
        person.get(
            "confidence",
            0,
        )
        or 0
    )

    return (
        1
        if person.get(
            "decision_maker"
        )
        is True
        else 0,

        2
        if seniority == "executive"
        else 1
        if seniority == "senior"
        else 0,

        1
        if verification_status
        == "valid"
        else 0,

        confidence,
    )


def enrich_prospect(
    prospect: dict,
) -> dict:

    domain = str(
        prospect.get(
            "domain",
            "",
        )
    ).strip().lower()

    if not domain:
        prospect[
            "email_status"
        ] = "NO_DOMAIN"

        return prospect

    likely_team = str(
        prospect.get(
            "likely_team",
            "",
        )
    )

    people = find_people(
        domain,
        likely_team,
    )

    if not people:
        prospect[
            "email_status"
        ] = "PERSON_NOT_FOUND"

        return prospect

    people.sort(
        key=lambda item: person_score(
            item,
            likely_team,
        ),
        reverse=True,
    )

    person = people[0]

    first_name = str(
        person.get(
            "first_name",
            "",
        )
        or ""
    ).strip()

    last_name = str(
        person.get(
            "last_name",
            "",
        )
        or ""
    ).strip()

    full_name = " ".join(
        value
        for value in (
            first_name,
            last_name,
        )
        if value
    )

    email = str(
        person.get(
            "value",
            "",
        )
        or ""
    ).strip()

    verification = (
        person.get(
            "verification"
        )
        or {}
    )

    verification_status = str(
        verification.get(
            "status",
            "",
        )
        or ""
    ).upper()

    prospect["contact"] = {
        "name": full_name,
        "title": str(
            person.get(
                "position",
                "",
            )
            or ""
        ),
        "linkedin_url": str(
            person.get(
                "linkedin",
                "",
            )
            or ""
        ),
        "department": str(
            person.get(
                "department",
                "",
            )
            or ""
        ),
        "seniority": str(
            person.get(
                "seniority",
                "",
            )
            or ""
        ),
        "decision_maker": (
            person.get(
                "decision_maker"
            )
        ),
        "provider": "hunter",
    }

    if email:
        prospect["email"] = email

        prospect[
            "email_status"
        ] = (
            verification_status
            or "FOUND"
        )

    else:
        prospect["email"] = None

        prospect[
            "email_status"
        ] = "EMAIL_NOT_FOUND"

    return prospect


def enrich_domains(
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
            "Select at least one company."
        )

    pool = load_pool()

    prospects = pool.get(
        "prospects",
        [],
    )

    attempted = 0
    found = 0
    failed = 0
    errors = []

    for prospect in prospects:

        domain = str(
            prospect.get(
                "domain",
                "",
            )
        ).strip().lower()

        if domain not in wanted:
            continue

        if (
            prospect.get(
                "priority"
            )
            == "REJECT"
        ):
            continue

        attempted += 1

        try:
            enrich_prospect(
                prospect
            )

            if prospect.get(
                "email"
            ):
                found += 1

        except Exception as exc:
            failed += 1

            prospect[
                "email_status"
            ] = "ERROR"

            errors.append(
                {
                    "company": (
                        prospect.get(
                            "company"
                        )
                    ),
                    "error": str(exc),
                }
            )

    save_pool(pool)

    return {
        "attempted": attempted,
        "emails_found": found,
        "failed": failed,
        "errors": errors,
    }
