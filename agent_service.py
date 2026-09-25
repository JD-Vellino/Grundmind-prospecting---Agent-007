import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent

ACTIVE_RESULT_DIR = (
    BASE_DIR / "active_result"
)

PROSPECT_RESULT_PATH = (
    ACTIVE_RESULT_DIR / "prospect_result.json"
)

COMMERCIAL_OPPORTUNITY_PATH = (
    ACTIVE_RESULT_DIR
    / "commercial_opportunity.json"
)

ACCOUNT_BRIEF_PATH = (
    ACTIVE_RESULT_DIR / "account_brief.json"
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required Agent 007 artifact not found: {path.name}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def get_latest_prospect_result() -> dict[str, Any]:
    return load_json(
        PROSPECT_RESULT_PATH
    )


def get_latest_commercial_opportunity() -> dict[str, Any]:
    return load_json(
        COMMERCIAL_OPPORTUNITY_PATH
    )


def get_latest_account_brief() -> dict[str, Any]:
    return load_json(
        ACCOUNT_BRIEF_PATH
    )


def get_dashboard() -> dict[str, Any]:
    prospect = get_latest_prospect_result()
    commercial = get_latest_commercial_opportunity()
    account_brief = get_latest_account_brief()

    prospect_company = prospect.get("company")
    commercial_company = commercial.get("company")
    brief_company = account_brief.get("company")

    companies = {
        prospect_company,
        commercial_company,
        brief_company,
    }

    companies.discard(None)

    if len(companies) != 1:
        raise ValueError(
            "Agent 007 artifacts do not belong "
            "to the same company."
        )

    return {
        "company": prospect_company,
        "activity": {
            "score": prospect.get("score"),
            "max_score": prospect.get("max_score"),
            "signals": prospect.get(
                "signals",
                {},
            ),
        },
        "commercial_opportunity": {
            "score": commercial.get(
                "commercial_opportunity_score"
            ),
            "max_score": commercial.get(
                "max_score"
            ),
            "pain_score": commercial.get(
                "pain_opportunity_score"
            ),
            "pain_max_score": commercial.get(
                "pain_opportunity_max_score"
            ),
            "proven_pain": commercial.get(
                "proven_pain"
            ),
            "signals": commercial.get(
                "signals",
                {},
            ),
            "classifications": commercial.get(
                "classifications",
                {},
            ),
        },
        "account_brief": account_brief.get(
            "brief",
            {},
        ),
        "evidence_catalog": commercial.get(
            "evidence_catalog",
            {},
        ),
    }


def get_research_run_dashboard(
    run_id: str,
) -> dict[str, Any]:

    from research_history import (
        load_research_run,
    )

    saved = load_research_run(
        run_id
    )

    artifacts = saved["artifacts"]

    prospect = artifacts.get(
        "prospect_result"
    )
    commercial = artifacts.get(
        "commercial_opportunity"
    )
    account_brief = artifacts.get(
        "account_brief"
    )

    if not all(
        isinstance(item, dict)
        for item in (
            prospect,
            commercial,
            account_brief,
        )
    ):
        raise ValueError(
            "Research run does not contain "
            "a complete dashboard result."
        )

    companies = {
        prospect.get("company"),
        commercial.get("company"),
        account_brief.get("company"),
    }

    companies.discard(None)

    if len(companies) != 1:
        raise ValueError(
            "Saved research artifacts do not "
            "belong to the same company."
        )

    return {
        "company": prospect.get("company"),
        "activity": {
            "score": prospect.get("score"),
            "max_score": prospect.get(
                "max_score"
            ),
            "signals": prospect.get(
                "signals",
                {},
            ),
        },
        "commercial_opportunity": {
            "score": commercial.get(
                "commercial_opportunity_score"
            ),
            "max_score": commercial.get(
                "max_score"
            ),
            "pain_score": commercial.get(
                "pain_opportunity_score"
            ),
            "pain_max_score": commercial.get(
                "pain_opportunity_max_score"
            ),
            "proven_pain": commercial.get(
                "proven_pain"
            ),
            "signals": commercial.get(
                "signals",
                {},
            ),
            "classifications": commercial.get(
                "classifications",
                {},
            ),
        },
        "account_brief": account_brief.get(
            "brief",
            {},
        ),
        "evidence_catalog": commercial.get(
            "evidence_catalog",
            {},
        ),
    }
