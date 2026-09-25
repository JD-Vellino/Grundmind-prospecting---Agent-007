import json
import re
import subprocess
import sys

from evidence_store import (
    get_verified_findings,
)

from company_config import get_company_config


# =========================================================
# SIGNAL CONFIGURATION
# =========================================================

SIGNALS = [
    {
        "key": "ai_hiring",
        "name": "AI Hiring",
        "script": "research_and_score.py",
        "max_score": 15,
    },
    {
        "key": "ai_deployment",
        "name": "AI Deployment",
        "script": "research_deployment.py",
        "max_score": 20,
    },
    {
        "key": "ai_value_roi",
        "name": "AI Value / ROI",
        "script": "research_roi.py",
        "max_score": 20,
    },
    {
        "key": "organisational_fit",
        "name": "Organisational Fit",
        "script": "research_organisational_fit.py",
        "max_score": 10,
    },
]


# =========================================================
# SCRIPT EXECUTION
# =========================================================

def run_signal_script(
    script: str,
) -> str:

    print(
        "\n"
        + "=" * 68
    )

    print(
        f"RUNNING {script}"
    )

    print(
        "=" * 68
    )

    process = subprocess.Popen(
        [
            sys.executable,
            script,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_lines = []

    assert process.stdout is not None

    for line in process.stdout:

        print(
            line,
            end="",
            flush=True,
        )

        output_lines.append(
            line
        )

    return_code = process.wait()

    output = "".join(
        output_lines
    )

    if return_code != 0:

        raise RuntimeError(
            f"{script} failed with "
            f"exit code {return_code}"
        )

    return output


# =========================================================
# SCORE PARSERS
# =========================================================

def parse_hiring_score(
    output: str,
) -> dict:

    matches = re.findall(
        r"AI Hiring\s*\n"
        r"Score:\s*(\d+)/(\d+)\s*\n"
        r"Evidence:\s*([A-Z_]+)\s*\n"
        r"Reason:\s*([^\n]+)",
        output,
    )

    if not matches:
        raise ValueError(
            "Could not parse AI Hiring score."
        )

    score, maximum, status, reason = (
        matches[-1]
    )

    return {
        "score": int(score),
        "max_score": int(maximum),
        "evidence_status": status,
        "reason": reason.strip(),
    }


def parse_named_score(
    output: str,
    name: str,
) -> dict:

    pattern = (
        rf"{re.escape(name)}:\s*"
        r"(\d+)/(\d+)\s*\n"
        r"Evidence:\s*([A-Z_]+)\s*\n"
        r"Reason:\s*([^\n]+)"
    )

    matches = re.findall(
        pattern,
        output,
    )

    if not matches:
        raise ValueError(
            f"Could not parse {name} score."
        )

    score, maximum, status, reason = (
        matches[-1]
    )

    return {
        "score": int(score),
        "max_score": int(maximum),
        "evidence_status": status,
        "reason": reason.strip(),
    }


def parse_signal_score(
    signal_name: str,
    output: str,
) -> dict:

    if signal_name == "AI Hiring":

        return parse_hiring_score(
            output
        )

    return parse_named_score(
        output=output,
        name=signal_name,
    )


# =========================================================
# EVIDENCE SNAPSHOT
# =========================================================

def compact_evidence(
    finding: dict,
) -> dict:

    supported_sources = []

    for verification in finding.get(
        "source_verifications",
        [],
    ):

        if (
            verification.get(
                "verification_status"
            )
            != "SUPPORTED"
        ):
            continue

        source_url = verification.get(
            "source_url"
        )

        if (
            source_url
            and source_url
            not in supported_sources
        ):
            supported_sources.append(
                source_url
            )

    return {
        "claim": finding.get(
            "claim",
            "",
        ),
        "supported_sources": (
            supported_sources
        ),
        "verified_at": finding.get(
            "verified_at"
        ),
    }


def load_signal_evidence(
    company: str,
    signal_key: str,
) -> list[dict]:

    findings = get_verified_findings(
        company=company,
        signal=signal_key,
    )

    return [
        compact_evidence(
            finding
        )
        for finding in findings
    ]


# =========================================================
# COMPANY ORCHESTRATOR
# =========================================================

def research_company(
    company: str,
) -> dict:

    company_config = get_company_config(
        company
    )

    canonical_company = (
        company_config.name
    )

    signal_results = {}

    for signal in SIGNALS:

        output = run_signal_script(
            signal["script"]
        )

        score_data = parse_signal_score(
            signal_name=signal["name"],
            output=output,
        )

        if (
            score_data["max_score"]
            != signal["max_score"]
        ):

            raise ValueError(
                f"Unexpected max score for "
                f"{signal['name']}: "
                f"{score_data['max_score']} "
                f"!= {signal['max_score']}"
            )

        signal_results[
            signal["key"]
        ] = {
            "name": signal["name"],
            **score_data,
            "established_evidence": (
                load_signal_evidence(
                    company=canonical_company,
                    signal_key=signal["key"],
                )
            ),
        }

    total_score = sum(
        result["score"]
        for result in signal_results.values()
    )

    total_max = sum(
        result["max_score"]
        for result in signal_results.values()
    )

    result = {
        "company": canonical_company,
        "score": total_score,
        "max_score": total_max,
        "signals": signal_results,
    }

    print(
        "\n\n"
        + "=" * 68
    )

    print(
        "GRUNDMIND PROSPECT SCORE"
    )

    print(
        "=" * 68
    )

    print(
        f"\nCompany: {canonical_company}\n"
    )

    for signal in SIGNALS:

        data = signal_results[
            signal["key"]
        ]

        print(
            f"{signal['name']:<24}"
            f"{data['score']:>2}/"
            f"{data['max_score']:<2}  "
            f"{data['evidence_status']}"
        )

    print(
        "\n"
        + "-" * 68
    )

    print(
        f"{'TOTAL':<24}"
        f"{total_score:>2}/"
        f"{total_max}"
    )

    print(
        "=" * 68
    )

    return result


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":

    import os

    result = research_company(
        os.environ.get(
            "AGENT007_COMPANY",
            "Logitech",
        )
    )

    with open(
        "latest_prospect_result.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
        )

    print(
        "\nSaved canonical result to:"
    )

    print(
        "latest_prospect_result.json"
    )
