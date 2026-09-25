from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from research_history import (
    archive_current_artifacts,
    clear_working_artifacts,
    create_run,
    promote_current_artifacts,
    restore_previous_active,
    write_run_metadata,
)


BASE_DIR = Path(__file__).resolve().parent

PIPELINE = [
    (
        "AI activity research",
        "research_company.py",
    ),
    (
        "Commercial pain research",
        "research_commercial_pain.py",
    ),
    (
        "Commercial opportunity scoring",
        "commercial_opportunity.py",
    ),
    (
        "Account brief generation",
        "account_brief.py",
    ),
]


_state_lock = threading.Lock()

_state = {
    "status": "idle",
    "company": None,
    "phase": None,
    "phase_index": 0,
    "phase_count": len(PIPELINE) + 1,
    "progress": 0,
    "message": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "run_id": None,
}


def _now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _snapshot() -> dict:
    with _state_lock:
        return dict(_state)


def get_research_status() -> dict:
    return _snapshot()


def _update(**values) -> None:
    with _state_lock:
        _state.update(values)


def start_research(
    company: str,
    website_hint: str | None = None,
) -> dict:

    company_query = company.strip()

    if not company_query:
        raise ValueError(
            "Company name is required."
        )

    with _state_lock:
        if _state["status"] == "running":
            raise RuntimeError(
                "A research run is already in progress."
            )

        run_dir = create_run(
            company_query
        )

        # latest_* files are scratch space only.
        # A new run must never inherit artifacts
        # produced by a previous company.
        clear_working_artifacts()

        _state.update(
            {
                "status": "running",
                "company": company_query,
                "phase": "Starting research",
                "phase_index": 0,
                "phase_count": len(PIPELINE) + 1,
                "progress": 0,
                "message": (
                    "Preparing Agent 007 research pipeline."
                ),
                "started_at": _now(),
                "finished_at": None,
                "error": None,
                "run_id": run_dir.name,
            }
        )

    worker = threading.Thread(
        target=_run_pipeline,
        args=(
            company_query,
            website_hint,
            run_dir,
        ),
        daemon=True,
        name="agent007-research",
    )

    worker.start()

    return _snapshot()


def _run_pipeline(
    company_query: str,
    website_hint: str | None,
    run_dir: Path,
) -> None:

    try:
        # -------------------------------------------------
        # Phase 1: company identity
        #
        # Existing companies resolve from the local config.
        # Unknown companies are researched, validated, and
        # persisted before any prospect research begins.
        # -------------------------------------------------

        _update(
            phase="Resolve company identity",
            phase_index=1,
            phase_count=len(PIPELINE) + 1,
            progress=0,
            message=(
                f"Resolving company identity for "
                f"{company_query}."
            ),
        )

        from company_identity import (
            resolve_company_identity,
        )

        company_config = (
            resolve_company_identity(
                company_query,
                website_hint=website_hint,
            )
        )

        company = company_config.name

        write_run_metadata(
            run_dir,
            {
                "company": company,
                "phase": (
                    "Resolve company identity"
                ),
            },
        )

        _update(
            company=company,
            progress=int(
                100 / (len(PIPELINE) + 1)
            ),
            message=(
                f"Identity resolved: {company}"
            ),
        )

        for index, (
            phase,
            script,
        ) in enumerate(
            PIPELINE,
            start=2,
        ):

            start_progress = int(
                ((index - 1) / (len(PIPELINE) + 1))
                * 100
            )

            write_run_metadata(
                run_dir,
                {
                    "phase": phase,
                    "phase_index": index,
                    "phase_count": (
                        len(PIPELINE) + 1
                    ),
                    "progress": start_progress,
                },
            )

            _update(
                phase=phase,
                phase_index=index,
                progress=start_progress,
                message=f"Running {script}",
            )

            print(
                f"\n[Agent 007] "
                f"Phase {index}/{len(PIPELINE) + 1}: "
                f"{phase}",
                flush=True,
            )

            process_env = os.environ.copy()
            process_env[
                "AGENT007_COMPANY"
            ] = company

            process = subprocess.Popen(
                [
                    sys.executable,
                    script,
                ],
                cwd=BASE_DIR,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            recent_lines: list[str] = []

            assert process.stdout is not None

            for line in process.stdout:
                clean = line.rstrip()

                if clean:
                    recent_lines.append(clean)

                    recent_lines = recent_lines[
                        -20:
                    ]

                    _update(
                        message=clean
                    )

                print(
                    line,
                    end="",
                    flush=True,
                )

            return_code = process.wait()

            if return_code != 0:
                detail = (
                    recent_lines[-1]
                    if recent_lines
                    else "No process output."
                )

                raise RuntimeError(
                    f"{script} failed with "
                    f"exit code {return_code}: "
                    f"{detail}"
                )

            _update(
                progress=int(
                    (
                        index
                        / (len(PIPELINE) + 1)
                    )
                    * 100
                ),
                message=f"{phase} complete.",
            )

        archive_current_artifacts(
            run_dir
        )

        # Only a completely successful run becomes
        # the dashboard-facing active result.
        promote_current_artifacts()

        finished_at = _now()

        write_run_metadata(
            run_dir,
            {
                "status": "completed",
                "phase": "Research complete",
                "phase_index": (
                    len(PIPELINE) + 1
                ),
                "phase_count": (
                    len(PIPELINE) + 1
                ),
                "progress": 100,
                "finished_at": finished_at,
                "error": None,
            },
        )

        _update(
            status="completed",
            phase="Research complete",
            progress=100,
            message=(
                "Agent 007 research completed "
                "successfully."
            ),
            finished_at=finished_at,
            error=None,
        )

    except Exception as exc:

        try:
            archive_current_artifacts(
                run_dir
            )
        except Exception as archive_exc:
            print(
                f"\n[Agent 007] Failed to archive "
                f"partial run: {archive_exc}",
                flush=True,
            )

        restored_previous = False

        try:
            restored_previous = (
                restore_previous_active(
                    run_dir
                )
            )
        except Exception as restore_exc:
            print(
                f"\n[Agent 007] Failed to restore "
                f"previous active result: "
                f"{restore_exc}",
                flush=True,
            )

        finished_at = _now()

        write_run_metadata(
            run_dir,
            {
                "status": "failed",
                "phase": "Research failed",
                "finished_at": finished_at,
                "error": str(exc),
                "previous_active_restored": (
                    restored_previous
                ),
            },
        )

        _update(
            status="failed",
            phase="Research failed",
            message=str(exc),
            finished_at=finished_at,
            error=str(exc),
        )

        print(
            f"\n[Agent 007] Research failed: {exc}",
            flush=True,
        )
