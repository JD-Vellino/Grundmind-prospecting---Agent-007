from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "research_runs"

ARTIFACTS = (
    "latest_prospect_result.json",
    "latest_commercial_opportunity.json",
    "latest_account_brief.json",
    "latest_account_brief.md",
)


def _now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _slug(value: str) -> str:
    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.lower(),
    )
    return value.strip("-") or "company"


def _load_company(path: Path) -> str | None:
    if not path.exists():
        return None

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None

    company = data.get("company")

    if not isinstance(company, str):
        return None

    return company.strip() or None


def active_artifacts_are_valid() -> bool:
    required = [
        BASE_DIR / "latest_prospect_result.json",
        BASE_DIR / "latest_commercial_opportunity.json",
        BASE_DIR / "latest_account_brief.json",
    ]

    companies = [
        _load_company(path)
        for path in required
    ]

    return (
        all(companies)
        and len(set(companies)) == 1
    )


def create_run(
    company_query: str,
) -> Path:

    RUNS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    run_dir = (
        RUNS_DIR
        / f"{stamp}-{_slug(company_query)}"
    )

    run_dir.mkdir()

    if active_artifacts_are_valid():

        previous = (
            run_dir / "previous_active"
        )

        previous.mkdir()

        for name in ARTIFACTS:
            source = BASE_DIR / name

            if source.exists():
                shutil.copy2(
                    source,
                    previous / name,
                )

    write_run_metadata(
        run_dir,
        {
            "query": company_query,
            "company": None,
            "status": "running",
            "started_at": _now(),
            "finished_at": None,
            "phase": "Resolve company identity",
            "error": None,
        },
    )

    return run_dir


def archive_current_artifacts(
    run_dir: Path,
) -> None:

    artifacts_dir = (
        run_dir / "artifacts"
    )

    artifacts_dir.mkdir(
        exist_ok=True
    )

    for name in ARTIFACTS:
        source = BASE_DIR / name

        if source.exists():
            shutil.copy2(
                source,
                artifacts_dir / name,
            )


def restore_previous_active(
    run_dir: Path,
) -> bool:

    previous = (
        run_dir / "previous_active"
    )

    if not previous.exists():
        return False

    for name in ARTIFACTS:
        destination = BASE_DIR / name

        if destination.exists():
            destination.unlink()

        source = previous / name

        if source.exists():
            shutil.copy2(
                source,
                destination,
            )

    return True


def write_run_metadata(
    run_dir: Path,
    values: dict,
) -> None:

    path = run_dir / "run.json"

    current = {}

    if path.exists():
        current = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    current.update(values)

    path.write_text(
        json.dumps(
            current,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


ACTIVE_DIR = BASE_DIR / "active_result"

ACTIVE_ARTIFACTS = {
    "latest_prospect_result.json":
        "prospect_result.json",
    "latest_commercial_opportunity.json":
        "commercial_opportunity.json",
    "latest_account_brief.json":
        "account_brief.json",
    "latest_account_brief.md":
        "account_brief.md",
}


def promote_current_artifacts() -> None:
    """
    Atomically promote a completed research result
    to the dashboard-facing active result.

    Working latest_* files may be partial during a run.
    active_result is changed only after full success.
    """

    required = (
        "latest_prospect_result.json",
        "latest_commercial_opportunity.json",
        "latest_account_brief.json",
    )

    companies = [
        _load_company(
            BASE_DIR / name
        )
        for name in required
    ]

    if (
        not all(companies)
        or len(set(companies)) != 1
    ):
        raise ValueError(
            "Cannot promote research result: "
            "completed artifacts do not belong "
            "to one company."
        )

    staging = (
        BASE_DIR / ".active_result_staging"
    )

    if staging.exists():
        shutil.rmtree(staging)

    staging.mkdir()

    for source_name, active_name in (
        ACTIVE_ARTIFACTS.items()
    ):
        source = BASE_DIR / source_name

        if source.exists():
            shutil.copy2(
                source,
                staging / active_name,
            )

    if ACTIVE_DIR.exists():
        shutil.rmtree(ACTIVE_DIR)

    staging.rename(
        ACTIVE_DIR
    )


def list_research_runs() -> list[dict]:
    """
    Return saved research runs newest first.
    """

    if not RUNS_DIR.exists():
        return []

    runs = []

    for run_dir in RUNS_DIR.iterdir():

        if not run_dir.is_dir():
            continue

        metadata_path = (
            run_dir / "run.json"
        )

        if not metadata_path.exists():
            continue

        try:
            metadata = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            continue

        artifacts_dir = (
            run_dir / "artifacts"
        )

        metadata = {
            **metadata,
            "run_id": run_dir.name,
            "has_artifacts": (
                artifacts_dir.exists()
                and any(
                    artifacts_dir.iterdir()
                )
            ),
        }

        runs.append(metadata)

    runs.sort(
        key=lambda item: (
            item.get("started_at") or ""
        ),
        reverse=True,
    )

    return runs


def load_research_run(
    run_id: str,
) -> dict:

    # Prevent path traversal.
    if (
        not run_id
        or Path(run_id).name != run_id
    ):
        raise ValueError(
            "Invalid research run ID."
        )

    run_dir = (
        RUNS_DIR / run_id
    )

    if not run_dir.exists():
        raise FileNotFoundError(
            f"Research run not found: {run_id}"
        )

    metadata_path = (
        run_dir / "run.json"
    )

    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Research run metadata not found: "
            f"{run_id}"
        )

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    artifacts_dir = (
        run_dir / "artifacts"
    )

    artifacts = {}

    artifact_names = {
        "prospect_result":
            "latest_prospect_result.json",
        "commercial_opportunity":
            "latest_commercial_opportunity.json",
        "account_brief":
            "latest_account_brief.json",
    }

    for key, filename in (
        artifact_names.items()
    ):

        path = (
            artifacts_dir / filename
        )

        if not path.exists():
            artifacts[key] = None
            continue

        try:
            artifacts[key] = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            artifacts[key] = None

    return {
        "run": {
            **metadata,
            "run_id": run_id,
        },
        "artifacts": artifacts,
    }


def clear_working_artifacts() -> None:
    """
    Remove scratch artifacts before a new research run.

    The dashboard reads active_result/, so clearing these
    working files cannot remove the current published result.
    """

    for name in ARTIFACTS:
        path = BASE_DIR / name

        if path.exists():
            path.unlink()
