from __future__ import annotations

import json
import os
import sys
import traceback

from datetime import datetime, timezone
from pathlib import Path

from discovery import discover
from prospect_pool import qualify_discovery
from prospect_runs import (
    complete_run,
    fail_run,
)


ROOT = Path(__file__).resolve().parent

STATUS_PATH = ROOT / "discovery_status.json"
DISCOVERY_PATH = ROOT / "latest_discovery.json"
POOL_PATH = ROOT / "master_prospect_pool.json"

CURRENT_RUN_ID: str | None = None


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def write_status(
    *,
    status: str,
    progress: int,
    message: str,
    found: int = 0,
    qualified: int = 0,
    error: str | None = None,
) -> None:

    payload = {
        "status": status,
        "run_id": CURRENT_RUN_ID,
        "progress": progress,
        "message": message,
        "found": found,
        "qualified": qualified,
        "error": error,
        "updated_at": now_iso(),
        "pid": os.getpid(),
    }

    temp = STATUS_PATH.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temp.replace(
        STATUS_PATH
    )


def build_target(
    request: dict,
) -> str:

    geography = str(
        request.get(
            "geography",
            "Europe",
        )
    )

    industry = str(
        request.get(
            "industry",
            "All industries",
        )
    )

    ai_signal = str(
        request.get(
            "ai_signal",
            "Any meaningful AI activity",
        )
    )

    pain_focus = str(
        request.get(
            "pain_focus",
            "Any relevant signal",
        )
    )

    department = str(
        request.get(
            "department",
            "Any department",
        )
    )

    lines = [
        "Find operating companies that are plausible "
        "GrundMind sales prospects.",
        "",
        f"Geography: {geography}",
        f"Industry: {industry}",
        f"AI signal focus: {ai_signal}",
        f"Pain/opportunity focus: {pain_focus}",
        f"Likely department: {department}",
        "",
        "The company should show meaningful evidence of AI, "
        "GenAI, automation, digital transformation, AI "
        "governance, workflow change, or related enterprise "
        "technology adoption.",
        "",
        "Commercially useful pain may include ROI/value "
        "uncertainty, adoption friction, workflow problems, "
        "governance, scaling difficulty, quality/remediation, "
        "or workforce/capability challenges.",
        "",
        "Do not require explicit public admission of failure. "
        "Indirect but commercially meaningful pain signals "
        "are useful for prospecting.",
    ]

    if industry == "All industries":
        lines.append(
            "Any operating industry is acceptable."
        )

    if department == "Any department":
        lines.append(
            "Any relevant business function is acceptable."
        )
    else:
        lines.append(
            "Prefer companies where the evidence is relevant "
            f"to {department}."
        )

    exclusions = []

    if request.get(
        "exclude_ai_vendors",
        True,
    ):
        exclusions.append(
            "companies whose primary business is selling AI software"
        )

    if request.get(
        "exclude_consultancies",
        True,
    ):
        exclusions.append(
            "consultancies and IT services firms"
        )

    if request.get(
        "exclude_research_media",
        True,
    ):
        exclusions.append(
            "research, media and training organisations"
        )

    if exclusions:
        lines.append("")
        lines.append(
            "Exclude: "
            + "; ".join(exclusions)
            + "."
        )

    return "\n".join(lines)


def existing_pool_keys() -> tuple[
    set[str],
    set[str],
]:

    if not POOL_PATH.exists():
        return set(), set()

    try:
        data = json.loads(
            POOL_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return set(), set()

    domains = set()
    companies = set()

    for item in data.get(
        "prospects",
        [],
    ):
        domain = str(
            item.get(
                "domain",
                "",
            )
        ).strip().lower()

        company = str(
            item.get(
                "company",
                "",
            )
        ).strip()

        if domain:
            domains.add(domain)

        if company:
            companies.add(company)

    return domains, companies


def filter_existing(
    result: dict,
) -> dict:

    domains, companies = (
        existing_pool_keys()
    )

    companies = {
        company.lower()
        for company in companies
    }

    candidates = result.get(
        "candidates",
        [],
    )

    if not isinstance(
        candidates,
        list,
    ):
        candidates = []

    filtered = []

    for item in candidates:

        if not isinstance(
            item,
            dict,
        ):
            continue

        domain = str(
            item.get(
                "domain",
                "",
            )
        ).strip().lower()

        company = str(
            item.get(
                "company",
                "",
            )
        ).strip().lower()

        if domain and domain in domains:
            continue

        if company and company in companies:
            continue

        filtered.append(item)

    result["candidates"] = filtered
    result["candidate_count"] = len(
        filtered
    )

    return result


def main() -> None:

    global CURRENT_RUN_ID

    if len(sys.argv) != 2:
        raise SystemExit(
            "discovery_job.py requires "
            "one JSON request argument."
        )

    request = json.loads(
        sys.argv[1]
    )

    CURRENT_RUN_ID = (
        str(
            request.get(
                "run_id",
                "",
            )
        ).strip()
        or None
    )

    target_count = int(
        request.get(
            "target_count",
            100,
        )
    )

    # When existing prospects are excluded, search
    # beyond the requested target so duplicates can
    # be removed while still returning roughly the
    # requested number of net-new companies.
    search_count = target_count

    if request.get(
        "exclude_existing",
        True,
    ):
        search_count = min(
            500,
            max(
                target_count * 2,
                target_count + 25,
            ),
        )

    try:
        write_status(
            status="running",
            progress=5,
            message=(
                "Preparing prospect search..."
            ),
        )

        target = build_target(
            request
        )

        write_status(
            status="running",
            progress=10,
            message=(
                "Searching across discovery lenses..."
            ),
        )

        exclude_domains: set[str] = set()
        exclude_companies: set[str] = set()

        if request.get(
            "exclude_existing",
            True,
        ):
            (
                exclude_domains,
                exclude_companies,
            ) = existing_pool_keys()

        result = discover(
            target_description=target,
            target_count=search_count,
            exclude_domains=exclude_domains,
            exclude_companies=exclude_companies,
        )

        if not isinstance(
            result,
            dict,
        ):
            raise RuntimeError(
                "Discovery returned an "
                "unexpected result."
            )

        write_status(
            status="running",
            progress=82,
            message=(
                "Filtering discovered companies..."
            ),
        )

        if request.get(
            "exclude_existing",
            True,
        ):
            result = filter_existing(
                result
            )

        candidates = result.get(
            "candidates",
            [],
        )

        if not isinstance(
            candidates,
            list,
        ):
            candidates = []

        # The UI target means the number of net-new
        # candidates we want after existing-company
        # removal, not the size of the initial search.
        candidates = candidates[
            :target_count
        ]

        result["candidates"] = candidates
        result["target"] = target
        result["requested_count"] = (
            target_count
        )
        result["candidate_count"] = len(
            candidates
        )

        DISCOVERY_PATH.write_text(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        write_status(
            status="running",
            progress=88,
            message=(
                f"Qualifying {len(candidates)} "
                "new companies..."
            ),
            found=len(candidates),
        )

        qualification = (
            qualify_discovery(
                run_id=(
                    CURRENT_RUN_ID
                )
            )
        )

        rejected = int(
            qualification.get(
                "rejected_this_run",
                0,
            )
        )

        qualified = max(
            0,
            len(candidates) - rejected,
        )

        complete_run(
            CURRENT_RUN_ID,
            prospect_keys=(
                qualification.get(
                    "run_keys",
                    [],
                )
            ),
            found=len(candidates),
            qualified=qualified,
        )

        write_status(
            status="completed",
            progress=100,
            message=(
                "Discovery and qualification complete."
            ),
            found=len(candidates),
            qualified=qualified,
        )

    except Exception as exc:

        traceback.print_exc()

        fail_run(
            CURRENT_RUN_ID,
            str(exc),
        )

        write_status(
            status="failed",
            progress=0,
            message="Discovery failed.",
            error=str(exc),
        )

        raise


if __name__ == "__main__":
    main()
