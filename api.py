from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent_service import (
    get_dashboard,
    get_research_run_dashboard,
)
from research_runner import (
    get_research_status,
    start_research,
)
from research_history import (
    list_research_runs,
    load_research_run,
)


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


app = FastAPI(
    title="Agent 007 API",
    version="0.1.0",
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "Agent 007",
    }


class ResearchRequest(BaseModel):
    company: str
    website: str | None = None


@app.get("/api/research/status")
def research_status() -> dict:
    return get_research_status()


@app.post(
    "/api/research",
    status_code=202,
)
def research(
    request: ResearchRequest,
) -> dict:
    try:
        return start_research(
            request.company,
            website_hint=request.website,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.get("/api/research/history")
def research_history() -> list[dict]:
    return list_research_runs()


@app.get("/api/research/history/{run_id}")
def research_history_run(
    run_id: str,
) -> dict:
    try:
        return load_research_run(
            run_id
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/research/history/{run_id}/dashboard"
)
def research_history_dashboard(
    run_id: str,
) -> dict:
    try:
        return get_research_run_dashboard(
            run_id
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.get("/api/dashboard")
def dashboard() -> dict:
    try:
        return get_dashboard()

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "No completed research result yet."
            ),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


if not FRONTEND_DIST.exists():
    raise RuntimeError(
        "Frontend build not found. "
        "Run: cd frontend && npm run build"
    )



# =========================================================
# PROSPECT POOL
# =========================================================

class ProspectEnrichmentRequest(BaseModel):
    domains: list[str]


@app.get("/api/prospects")
def prospect_pool(
    run_id: str | None = None,
) -> dict:

    from prospect_runs import (
        load_run_pool,
    )

    try:
        return load_run_pool(
            run_id
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get("/api/prospects/runs")
def prospect_pool_runs() -> dict:

    from prospect_runs import (
        list_runs,
    )

    return list_runs()


@app.post("/api/prospects/enrich")
def prospect_enrichment(
    request: ProspectEnrichmentRequest,
) -> dict:

    from prospect_contacts import (
        enrich_domains,
    )

    try:
        return enrich_domains(
            request.domains
        )

    except (
        ValueError,
        RuntimeError,
    ) as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc



# =========================================================
# GENERAL PROSPECT DISCOVERY
# =========================================================

class DiscoveryRequest(BaseModel):
    target_count: int = 100
    geography: str = "Europe"
    industry: str = "All industries"
    ai_signal: str = "Any meaningful AI activity"
    pain_focus: str = "Any relevant signal"
    department: str = "Any department"

    exclude_ai_vendors: bool = True
    exclude_consultancies: bool = True
    exclude_research_media: bool = True
    exclude_existing: bool = True

    # "news": search AI news for companies (discovery.py).
    # "company_list": check each company of a list
    # (list_discovery.py); target_count = companies to check.
    mode: str = "news"
    company_list: str = ""


DISCOVERY_STATUS_PATH = (
    Path(__file__).resolve().parent
    / "discovery_status.json"
)


@app.post("/api/discovery")
def start_discovery(
    request: DiscoveryRequest,
) -> dict:

    import json
    import subprocess
    import sys

    root = Path(
        __file__
    ).resolve().parent

    if request.mode == "company_list":
        from list_discovery import COMPANY_LISTS

        if request.company_list not in COMPANY_LISTS:
            raise HTTPException(
                status_code=400,
                detail="Unknown company list.",
            )

    elif request.mode != "news":
        raise HTTPException(
            status_code=400,
            detail="Unknown discovery mode.",
        )

    if DISCOVERY_STATUS_PATH.exists():

        try:
            current = json.loads(
                DISCOVERY_STATUS_PATH.read_text(
                    encoding="utf-8"
                )
            )

            if (
                current.get("status")
                == "running"
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A prospect discovery "
                        "run is already active."
                    ),
                )

        except HTTPException:
            raise

        except Exception:
            pass

    payload = request.model_dump()

    from prospect_runs import (
        create_run,
    )

    run = create_run(
        payload
    )

    payload["run_id"] = (
        run["run_id"]
    )

    initial = {
        "status": "running",
        "run_id": run["run_id"],
        "progress": 1,
        "message": (
            "Starting prospect discovery..."
        ),
        "found": 0,
        "qualified": 0,
        "error": None,
    }

    DISCOVERY_STATUS_PATH.write_text(
        json.dumps(
            initial,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    log_path = (
        root
        / "discovery_api.log"
    )

    log_handle = log_path.open(
        "a",
        encoding="utf-8",
    )

    try:
        subprocess.Popen(
            [
                sys.executable,
                str(
                    root
                    / "discovery_job.py"
                ),
                json.dumps(payload),
            ],
            cwd=str(root),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    finally:
        log_handle.close()

    return initial


@app.get("/api/discovery/lists")
def discovery_lists() -> dict:

    from discovery_job import existing_pool_keys
    from list_discovery import list_summaries

    _, companies = existing_pool_keys()

    return {
        "lists": list_summaries(companies),
    }


@app.get("/api/discovery/status")
def discovery_status() -> dict:

    import json

    if not DISCOVERY_STATUS_PATH.exists():
        return {
            "status": "idle",
            "run_id": None,
            "progress": 0,
            "message": None,
            "found": 0,
            "qualified": 0,
            "error": None,
        }

    try:
        return json.loads(
            DISCOVERY_STATUS_PATH.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to read "
                "discovery status."
            ),
        ) from exc



# =========================================================
# OUTREACH DRAFTS
# =========================================================

class ProspectDraftRequest(BaseModel):
    domains: list[str]
    subject: str
    body: str
    use_ai_signal: bool = True
    use_pain_signal: bool = True
    use_role: bool = True


@app.post("/api/prospects/drafts")
def prospect_drafts(
    request: ProspectDraftRequest,
) -> dict:

    from prospect_outreach import (
        generate_drafts,
    )

    try:
        return generate_drafts(
            domains=request.domains,
            subject=request.subject,
            body=request.body,
            use_ai_signal=(
                request.use_ai_signal
            ),
            use_pain_signal=(
                request.use_pain_signal
            ),
            use_role=request.use_role,
        )

    except (
        ValueError,
        RuntimeError,
    ) as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc



# =========================================================
# OUTREACH SEND
# =========================================================

class ProspectSendRequest(BaseModel):
    domains: list[str]


@app.post("/api/prospects/send")
def prospect_send(
    request: ProspectSendRequest,
) -> dict:

    from prospect_send import (
        send_domains,
    )

    try:
        return send_domains(
            request.domains
        )

    except (
        ValueError,
        RuntimeError,
    ) as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


app.mount(
    "/",
    StaticFiles(
        directory=FRONTEND_DIST,
        html=True,
    ),
    name="frontend",
)
