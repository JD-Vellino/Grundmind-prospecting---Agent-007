import json
import os
import re

from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit


STORE_PATH = "evidence_store.json"


# =========================================================
# STORE IO
# =========================================================

def load_store() -> dict:

    if not os.path.exists(STORE_PATH):
        return {
            "companies": {}
        }

    with open(
        STORE_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_store(store: dict) -> None:

    with open(
        STORE_PATH,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            store,
            file,
            indent=2,
        )


# =========================================================
# DETERMINISTIC EVIDENCE IDENTITY
# =========================================================

def normalize_url(url: str) -> str:

    if not url:
        return ""

    parts = urlsplit(
        url.strip()
    )

    path = parts.path.rstrip("/")

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            "",
            "",
        )
    )


def normalize_claim(claim: str) -> str:

    tokens = re.findall(
        r"[a-z0-9%$]+",
        claim.lower(),
    )

    return " ".join(tokens)


def extract_numbers(text: str) -> set[str]:

    numbers = re.findall(
        r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
        text,
    )

    return {
        number.replace(",", "")
        for number in numbers
    }

def extract_keywords(text: str) -> set[str]:

    stopwords = {
        "that",
        "this",
        "with",
        "from",
        "into",
        "over",
        "through",
        "their",
        "they",
        "them",
        "were",
        "been",
        "being",
        "have",
        "has",
        "had",
        "within",
        "about",
        "using",
    }

    return {
        token
        for token in re.findall(
            r"[a-z]+",
            text.lower(),
        )
        if (
            len(token) >= 4
            and token not in stopwords
        )
    }

def get_source_urls(
    finding: dict,
) -> set[str]:

    return {
        normalize_url(
            source.get(
                "source_url",
                "",
            )
        )
        for source in finding.get(
            "sources",
            [],
        )
        if source.get(
            "source_url"
        )
    }


def same_evidence(
    first: dict,
    second: dict,
) -> bool:

    first_urls = get_source_urls(first)
    second_urls = get_source_urls(second)

    # Different sources are not automatically duplicates.
    if not (first_urls & second_urls):
        return False

    first_claim = normalize_claim(
        first.get("claim", "")
    )

    second_claim = normalize_claim(
        second.get("claim", "")
    )

    if not first_claim or not second_claim:
        return False

    if first_claim == second_claim:
        return True

    similarity = SequenceMatcher(
        None,
        first_claim,
        second_claim,
    ).ratio()

    if similarity >= 0.82:
        return True

    first_numbers = extract_numbers(
        first_claim
    )

    second_numbers = extract_numbers(
        second_claim
    )

    shared_numbers = (
        first_numbers
        & second_numbers
    )

    # Same fetched source + multiple identical quantitative
    # values is treated as the same underlying evidence.
    if len(shared_numbers) >= 2:
        return True

    first_keywords = extract_keywords(
        first.get("claim", "")
    )

    second_keywords = extract_keywords(
        second.get("claim", "")
    )

    shared_keywords = (
        first_keywords
        & second_keywords
    )

    # Same fetched source + at least one identical
    # quantitative value + strong initiative overlap
    # is treated as the same underlying evidence.
    if (
        len(shared_numbers) >= 1
        and len(shared_keywords) >= 4
    ):
        return True

    return False

def deduplicate_findings(
    findings: list[dict],
) -> list[dict]:

    unique = []

    for finding in findings:

        duplicate = any(
            same_evidence(
                finding,
                saved,
            )
            for saved in unique
        )

        if not duplicate:
            unique.append(
                finding
            )

    return unique


# =========================================================
# PERSISTENCE
# =========================================================

def save_verified_findings(
    company: str,
    signal: str,
    findings: list[dict],
) -> None:

    store = load_store()

    companies = store.setdefault(
        "companies",
        {},
    )

    company_data = companies.setdefault(
        company,
        {},
    )

    existing = company_data.setdefault(
        signal,
        [],
    )

    # Also clean duplicates already accumulated in
    # previous runs.
    existing = deduplicate_findings(
        existing
    )

    company_data[signal] = existing

    for finding in findings:

        duplicate = any(
            same_evidence(
                finding,
                saved,
            )
            for saved in existing
        )

        if duplicate:
            continue

        stored_finding = {
            **finding,
            "verified_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        existing.append(
            stored_finding
        )

    save_store(
        store
    )


def get_verified_findings(
    company: str,
    signal: str,
) -> list[dict]:

    store = load_store()

    findings = (
        store
        .get("companies", {})
        .get(company, {})
        .get(signal, [])
    )

    # Defensive read boundary. Even if an old store contains
    # duplicates, callers receive a deduplicated evidence set.
    return deduplicate_findings(
        findings
    )


# =========================================================
# SMOKE TEST
# =========================================================

if __name__ == "__main__":

    findings = get_verified_findings(
        company="Logitech",
        signal="ai_value_roi",
    )

    print(
        json.dumps(
            findings,
            indent=2,
        )
    )