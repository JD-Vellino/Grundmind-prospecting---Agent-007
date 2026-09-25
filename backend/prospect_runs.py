from __future__ import annotations

import json
import re
import uuid

from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNS_PATH = ROOT / "prospect_runs.json"
POOL_PATH = ROOT / "master_prospect_pool.json"


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_company(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        value.lower(),
    )


def prospect_key(item: dict) -> str:
    domain = str(
        item.get("domain", "")
    ).strip().lower()

    if domain:
        return f"domain:{domain}"

    return (
        "company:"
        + normalize_company(
            str(
                item.get(
                    "company",
                    "",
                )
            )
        )
    )


def load_master_pool() -> dict:
    if not POOL_PATH.exists():
        return {
            "prospects": [],
        }

    try:
        data = json.loads(
            POOL_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {
            "prospects": [],
        }

    if not isinstance(data, dict):
        return {
            "prospects": [],
        }

    return data


def _save_registry(
    registry: dict,
) -> None:
    temp = RUNS_PATH.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            registry,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temp.replace(
        RUNS_PATH
    )


def _public_run(
    run: dict,
) -> dict:
    return {
        key: value
        for key, value in run.items()
        if key != "prospect_keys"
    }


def _legacy_registry() -> dict:
    pool = load_master_pool()

    prospects = [
        item
        for item in pool.get(
            "prospects",
            [],
        )
        if isinstance(item, dict)
    ]

    if not prospects:
        return {
            "version": 1,
            "active_run_id": None,
            "runs": [],
        }

    keys = []

    for item in prospects:
        key = prospect_key(item)
        if key:
            keys.append(key)

    created_at = (
        pool.get("created_at")
        or pool.get("updated_at")
        or now_iso()
    )

    completed_at = (
        pool.get("updated_at")
        or created_at
    )

    run_id = "legacy-import"

    return {
        "version": 1,
        "active_run_id": run_id,
        "runs": [
            {
                "run_id": run_id,
                "label": (
                    "Previous pool "
                    "(before run tracking)"
                ),
                "status": "completed",
                "started_at": created_at,
                "completed_at": completed_at,
                "request": None,
                "found": len(prospects),
                "qualified": sum(
                    1
                    for item in prospects
                    if item.get("priority")
                    != "REJECT"
                ),
                "prospect_keys": keys,
                "legacy": True,
            }
        ],
    }


def load_registry() -> dict:
    if RUNS_PATH.exists():
        try:
            data = json.loads(
                RUNS_PATH.read_text(
                    encoding="utf-8"
                )
            )

            if (
                isinstance(data, dict)
                and isinstance(
                    data.get("runs"),
                    list,
                )
            ):
                return data

        except Exception:
            pass

    registry = _legacy_registry()
    _save_registry(registry)
    return registry


def create_run(
    request: dict,
) -> dict:
    registry = load_registry()

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    run_id = (
        timestamp
        + "-"
        + uuid.uuid4().hex[:6]
    )

    started_at = now_iso()

    run = {
        "run_id": run_id,
        "label": (
            f"{request.get('geography', 'Search')} · "
            f"{request.get('industry', 'All industries')}"
        ),
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "request": dict(request),
        "found": 0,
        "qualified": 0,
        "prospect_keys": [],
        "legacy": False,
    }

    registry.setdefault(
        "runs",
        [],
    ).append(run)

    registry[
        "active_run_id"
    ] = run_id

    _save_registry(registry)

    return _public_run(run)


def _find_run(
    registry: dict,
    run_id: str,
) -> dict | None:
    for run in registry.get(
        "runs",
        [],
    ):
        if (
            isinstance(run, dict)
            and run.get("run_id")
            == run_id
        ):
            return run

    return None


def complete_run(
    run_id: str | None,
    *,
    prospect_keys: list[str],
    found: int,
    qualified: int,
) -> None:
    if not run_id:
        return

    registry = load_registry()
    run = _find_run(
        registry,
        run_id,
    )

    if not run:
        return

    seen = set()
    keys = []

    for key in prospect_keys:
        value = str(key).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        keys.append(value)

    run["status"] = "completed"
    run["completed_at"] = now_iso()
    run["found"] = int(found)
    run["qualified"] = int(
        qualified
    )
    run["prospect_keys"] = keys

    registry[
        "active_run_id"
    ] = run_id

    _save_registry(registry)


def fail_run(
    run_id: str | None,
    error: str,
) -> None:
    if not run_id:
        return

    registry = load_registry()
    run = _find_run(
        registry,
        run_id,
    )

    if not run:
        return

    run["status"] = "failed"
    run["completed_at"] = now_iso()
    run["error"] = str(error)

    _save_registry(registry)


def list_runs() -> dict:
    registry = load_registry()

    runs = [
        _public_run(run)
        for run in reversed(
            registry.get(
                "runs",
                [],
            )
        )
        if isinstance(run, dict)
    ]

    return {
        "active_run_id": (
            registry.get(
                "active_run_id"
            )
        ),
        "runs": runs,
    }


def load_run_pool(
    run_id: str | None = None,
) -> dict:
    registry = load_registry()

    active_run_id = (
        registry.get(
            "active_run_id"
        )
    )

    selected_run_id = (
        run_id
        or active_run_id
    )

    public_runs = [
        _public_run(run)
        for run in reversed(
            registry.get(
                "runs",
                [],
            )
        )
        if isinstance(run, dict)
    ]

    if not selected_run_id:
        return {
            "run_id": None,
            "is_current": True,
            "run": None,
            "runs": public_runs,
            "prospects": [],
        }

    run = _find_run(
        registry,
        selected_run_id,
    )

    if not run:
        raise ValueError(
            "Unknown prospect run: "
            f"{selected_run_id}"
        )

    pool = load_master_pool()

    by_key = {}

    for prospect in pool.get(
        "prospects",
        [],
    ):
        if not isinstance(
            prospect,
            dict,
        ):
            continue

        key = prospect_key(
            prospect
        )

        if key:
            by_key[key] = prospect

    prospects = []

    for key in run.get(
        "prospect_keys",
        [],
    ):
        prospect = by_key.get(
            key
        )

        if prospect is not None:
            prospects.append(
                prospect
            )

    return {
        "run_id": selected_run_id,
        "is_current": (
            selected_run_id
            == active_run_id
        ),
        "run": _public_run(run),
        "runs": public_runs,
        "prospects": prospects,
    }
