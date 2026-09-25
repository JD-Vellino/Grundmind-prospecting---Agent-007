import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from evidence_quality import (
    classify_evidence_status,
    strongest_source_type,
)
from evidence_store import (
    get_verified_findings,
)
from prospect_score import EvidenceStatus
from company_config import get_company_config


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


# =========================================================
# COMPANY / SOURCE POLICY
# =========================================================

COMPANY_CONFIG = get_company_config(
    os.environ.get(
        "AGENT007_COMPANY",
        "Logitech",
    )
)

COMPANY = COMPANY_CONFIG.name

SOURCE_POLICY = COMPANY_CONFIG.policy(
    "commercial_opportunity"
)

OFFICIAL_DOMAINS = list(
    SOURCE_POLICY.official_domains
)

OFFICIAL_SOURCE_PREFIXES = list(
    SOURCE_POLICY.official_source_prefixes
)


# =========================================================
# COMMERCIAL OPPORTUNITY TAXONOMY
# =========================================================

# Commercial opportunity points require evidenced pain.
#
# Exposure, normal adoption activity, governance activity,
# partial value, and absence of broad ROI evidence are useful
# qualification/context signals but are NOT proof of failure.

HIRING_FACTORS = {
    "UNKNOWN": 0.00,
    "NORMAL_GROWTH": 0.00,
    "ADOPTION_ENABLEMENT": 0.00,
    "GOVERNANCE_RESPONSE": 0.00,
    "TRANSFORMATION_REMEDIATION": 0.70,
    "EXPLICIT_PROBLEM_RESPONSE": 1.00,
}

DEPLOYMENT_FACTORS = {
    "UNKNOWN": 0.00,
    "HEALTHY": 0.00,
    "FRICTION": 0.55,
    "UNEVEN": 0.75,
    "STALLED": 0.90,
    "FAILED": 1.00,
}

ROI_FACTORS = {
    "UNKNOWN": 0.00,
    "STRONG_RETURN": 0.00,
    "PARTIAL_VALUE": 0.00,
    "ROI_NOT_ESTABLISHED": 0.00,
    "ROI_CHALLENGED": 0.80,
    "ROI_FAILURE": 1.00,
}


# Categories that assert actual pain / organisational response.
# Weak evidence must not produce a strong prospect score.

# Classifications that LOWER commercial opportunity by asserting
# that the observed activity is healthy / ordinary / strongly successful.
#
# These also require credible evidence. Weak evidence must not be
# allowed to "exonerate" a prospect any more than weak evidence can
# establish pain.

EXCULPATORY = {
    "hiring": {
        "NORMAL_GROWTH",
    },
    "deployment": {
        "HEALTHY",
    },
    "roi": {
        "STRONG_RETURN",
    },
}


ASSERTIVE_PAIN = {
    "hiring": {
        "ADOPTION_ENABLEMENT",
        "GOVERNANCE_RESPONSE",
        "TRANSFORMATION_REMEDIATION",
        "EXPLICIT_PROBLEM_RESPONSE",
    },
    "deployment": {
        "FRICTION",
        "UNEVEN",
        "STALLED",
        "FAILED",
    },
    "roi": {
        "ROI_CHALLENGED",
        "ROI_FAILURE",
    },
}


EVIDENCE_QUALITY_FACTORS = {
    "VERIFIED": 1.00,
    "CORROBORATED": 0.85,
    "UNVERIFIED": 0.55,
    "CONFLICTING": 0.40,
}


# =========================================================
# INPUT
# =========================================================

def load_prospect_result() -> dict:

    path = Path(
        "latest_prospect_result.json"
    )

    if not path.exists():
        raise FileNotFoundError(
            "latest_prospect_result.json not found."
        )

    return json.loads(
        path.read_text()
    )


# =========================================================
# ITEM-LEVEL EVIDENCE QUALITY
# =========================================================

def item_evidence_status(
    urls: list[str],
) -> str:

    if not urls:
        return "UNVERIFIED"

    status = classify_evidence_status(
        urls=urls,
        official_domains=OFFICIAL_DOMAINS,
        official_source_prefixes=(
            OFFICIAL_SOURCE_PREFIXES
        ),
    )

    if hasattr(status, "value"):
        return status.value

    return str(status)


def item_source_type(
    urls: list[str],
) -> str | None:

    return strongest_source_type(
        urls=urls,
        official_domains=OFFICIAL_DOMAINS,
        official_source_prefixes=(
            OFFICIAL_SOURCE_PREFIXES
        ),
    )


def build_evidence_catalog(
    result: dict,
) -> dict:

    catalog = {}

    for signal_key, signal in (
        result.get(
            "signals",
            {}
        ).items()
    ):

        for index, finding in enumerate(
            signal.get(
                "established_evidence",
                []
            ),
            start=1,
        ):

            evidence_ref = (
                f"{signal_key}:E{index}"
            )

            urls = finding.get(
                "supported_sources",
                [],
            )

            catalog[evidence_ref] = {
                "signal": signal_key,
                "claim": finding.get(
                    "claim",
                    "",
                ),
                "supported_sources": urls,
                "evidence_status": (
                    item_evidence_status(
                        urls
                    )
                ),
                "source_type": (
                    item_source_type(
                        urls
                    )
                ),
            }

    # -----------------------------------------------------
    # Dedicated pain/failure evidence stream
    # -----------------------------------------------------

    pain_findings = get_verified_findings(
        company=result["company"],
        signal="commercial_pain",
    )

    for index, finding in enumerate(
        pain_findings,
        start=1,
    ):

        evidence_ref = (
            f"commercial_pain:E{index}"
        )

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

        catalog[evidence_ref] = {
            "signal": "commercial_pain",
            "claim": finding.get(
                "claim",
                "",
            ),
            "supported_sources": (
                supported_sources
            ),
            "evidence_status": (
                item_evidence_status(
                    supported_sources
                )
            ),
            "source_type": (
                item_source_type(
                    supported_sources
                )
            ),
        }

    return catalog


# =========================================================
# CLOSED-WORLD COMMERCIAL CLASSIFIER
# =========================================================

def classify_commercial_pain(
    company: str,
    catalog: dict,
) -> dict:

    classifier_input = [
        {
            "evidence_ref": ref,
            **item,
        }
        for ref, item
        in catalog.items()
    ]

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a closed-world commercial "
                    "opportunity evidence classifier. "
                    "Do not research. "
                    "Do not use outside knowledge. "
                    "The supplied findings have already "
                    "passed source fetching and claim "
                    "verification. "
                    "Classify only what the supplied "
                    "evidence actually establishes. "
                    "Absence of evidence is never evidence "
                    "of failure. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Target company:
{company}

We are identifying companies that may be good prospects for an
evidence-based AI adoption diagnostic.

The commercial pattern we care about is:

MEANINGFUL AI EXPOSURE / INVESTMENT
+
EVIDENCED FAILURE, FRICTION, WEAK VALUE, OR REMEDIATION NEED

Do NOT turn normal AI activity into evidence of failure.


=========================================================
HIRING
=========================================================

Classify using:

- ai_hiring evidence
- commercial_pain evidence that explicitly concerns hiring,
  enablement, governance response, transformation remediation,
  or a problem that caused a role/programme to be created.

Do not use unrelated commercial_pain evidence.

UNKNOWN
= evidence does not establish one of the categories below.

NORMAL_GROWTH
= ordinary AI technical or capability hiring without evidence of an
  adoption, governance, transformation, value, or remediation need.

ADOPTION_ENABLEMENT
= role is explicitly intended to enable organisational AI adoption,
  training, workforce capability, or AI use.

This does NOT by itself prove adoption is failing.

GOVERNANCE_RESPONSE
= role explicitly focuses on AI governance, responsible AI, controls,
  policy, risk, or oversight.

This indicates organisational response to governance requirements but
does NOT by itself prove governance failure.

TRANSFORMATION_REMEDIATION
= evidence explicitly says the role exists to improve weak adoption,
  inconsistent implementation, transformation problems, poor value
  realization, workflow problems, or another identified deficiency.

EXPLICIT_PROBLEM_RESPONSE
= evidence explicitly connects the hiring to a known AI failure,
  underperformance, serious adoption problem, governance failure,
  failed transformation, or inability to achieve expected value.


=========================================================
DEPLOYMENT
=========================================================

Classify using:

- ai_deployment evidence
- commercial_pain evidence that explicitly concerns deployment,
  adoption, rollout, workflow friction, scaling, tool use,
  abandonment, or operational implementation.

Do not use unrelated commercial_pain evidence.

UNKNOWN
= deployment exists or may exist, but the supplied evidence does not
  establish either health or friction.

HEALTHY
= credible evidence explicitly establishes that the relevant internal
  AI deployment footprint is successful, effective, or broadly adopted
  without material reported friction.

Do not use HEALTHY merely because deployment exists.

Do not classify the whole deployment dimension as HEALTHY merely
because one workflow or one deployment has successful operational
metrics.

A successful accounts-payable workflow does not establish that other
AI deployments are healthy.

If some deployments appear successful but the overall deployment
health is not established, use UNKNOWN.

HEALTHY must reflect evidence about the relevant deployment footprint,
not absence of negative reporting.

FRICTION
= evidence explicitly establishes implementation difficulty,
  adoption difficulty, workflow friction, user resistance, tool
  problems, governance friction, or operational difficulty.

UNEVEN
= evidence explicitly establishes materially inconsistent adoption,
  performance, rollout, value, or use between teams, functions, or
  populations.

STALLED
= evidence explicitly establishes pilots or deployment that failed
  to progress, materially delayed rollout, inability to scale, or
  repeated experimentation without production progression.

FAILED
= evidence explicitly establishes abandonment, rollback,
  discontinuation, material failure, or a deployment judged
  unsuccessful.


=========================================================
ROI / VALUE
=========================================================

Classify using:

- ai_value_roi evidence
- commercial_pain evidence that explicitly concerns ROI,
  value realization, benefits, costs, expected return,
  underperformance, or inability to demonstrate value.

Do not use unrelated commercial_pain evidence.

UNKNOWN
= supplied evidence does not establish enough to classify.

STRONG_RETURN
= evidence explicitly establishes strong, broad, well-measured AI
  financial return or benefits realization.

PARTIAL_VALUE
= evidence establishes real AI value or operational benefit in one or
  more specific workflows or functions, but does NOT establish broad
  enterprise ROI.

This is NOT evidence of failure.

ROI_NOT_ESTABLISHED
= meaningful AI exposure exists in the supplied evidence, but no
  evidence establishes explicit financial ROI or broad benefits
  realization.

This means exactly "not established from supplied evidence."
It does NOT mean poor ROI.

ROI_CHALLENGED
= evidence explicitly says ROI is difficult to prove, below
  expectations, inconsistent, disputed, weak, insufficient, delayed,
  or otherwise problematic.

ROI_FAILURE
= evidence explicitly establishes poor financial return, material
  value destruction, failed ROI expectations, or abandonment because
  expected value was not achieved.


=========================================================
STRICT RULES
=========================================================

- No public ROI evidence != bad ROI.
- AI governance hiring != governance failure.
- AI deployment != deployment success.
- AI deployment != deployment failure.
- Scaling != friction.
- Organisational size != adoption difficulty.
- Leadership interest != pain.
- A vendor success story is not failure evidence.
- Do not infer problems because GrundMind could theoretically solve
  them.
- False negatives are preferable to false positives.

COMMERCIAL_PAIN EVIDENCE:

The commercial_pain stream contains findings gathered specifically
while searching for failure, friction, underperformance, or remediation
need.

However, the label commercial_pain does NOT itself prove a category.

You must still inspect the actual claim.

Use a commercial_pain finding only for the dimension whose condition
the claim explicitly establishes.

Examples:

- explicit ROI difficulty may support ROI_CHALLENGED
- explicit stalled rollout may support STALLED
- explicit low adoption may support FRICTION or UNEVEN
- explicit remediation hiring may support
  TRANSFORMATION_REMEDIATION

Do not cross-apply pain merely because it exists in this stream.

Each classification must cite only evidence_refs belonging to the
relevant signal.

Return exactly:

{{
  "hiring": {{
    "status": "UNKNOWN|NORMAL_GROWTH|ADOPTION_ENABLEMENT|GOVERNANCE_RESPONSE|TRANSFORMATION_REMEDIATION|EXPLICIT_PROBLEM_RESPONSE",
    "evidence_refs": [],
    "reason": ""
  }},
  "deployment": {{
    "status": "UNKNOWN|HEALTHY|FRICTION|UNEVEN|STALLED|FAILED",
    "evidence_refs": [],
    "reason": ""
  }},
  "roi": {{
    "status": "UNKNOWN|STRONG_RETURN|PARTIAL_VALUE|ROI_NOT_ESTABLISHED|ROI_CHALLENGED|ROI_FAILURE",
    "evidence_refs": [],
    "reason": ""
  }}
}}

ESTABLISHED EVIDENCE:

{json.dumps(classifier_input, indent=2)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=2500,
        timeout=120,
        extra_body={
            "thinking": {
                "type": "disabled"
            }
        },
    )

    content = (
        response.choices[0]
        .message.content
        or ""
    ).strip()

    if not content:
        raise ValueError(
            "Commercial classifier returned "
            "an empty response."
        )

    return json.loads(
        content
    )


# =========================================================
# CLASSIFICATION VALIDATION
# =========================================================

ALLOWED = {
    "hiring": set(
        HIRING_FACTORS
    ),
    "deployment": set(
        DEPLOYMENT_FACTORS
    ),
    "roi": set(
        ROI_FACTORS
    ),
}

ALLOWED_REF_PREFIXES = {
    "hiring": (
        "ai_hiring:",
        "commercial_pain:",
    ),
    "deployment": (
        "ai_deployment:",
        "commercial_pain:",
    ),
    "roi": (
        "ai_value_roi:",
        "commercial_pain:",
    ),
}


def validate_classifications(
    classifications: dict,
    catalog: dict,
) -> None:

    for dimension in [
        "hiring",
        "deployment",
        "roi",
    ]:

        item = classifications.get(
            dimension
        )

        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                f"Missing classification: "
                f"{dimension}"
            )

        status = str(
            item.get(
                "status",
                "UNKNOWN",
            )
        ).upper()

        if status not in ALLOWED[
            dimension
        ]:
            raise ValueError(
                f"Invalid {dimension} "
                f"classification: {status}"
            )

        refs = item.get(
            "evidence_refs",
            [],
        )

        if not isinstance(
            refs,
            list,
        ):
            raise ValueError(
                f"{dimension} evidence_refs "
                "must be a list."
            )

        for ref in refs:

            if ref not in catalog:
                raise ValueError(
                    f"Unknown evidence ref: "
                    f"{ref}"
                )

            if not ref.startswith(
                ALLOWED_REF_PREFIXES[
                    dimension
                ]
            ):
                raise ValueError(
                    f"{dimension} illegally cited "
                    f"cross-signal evidence: {ref}"
                )

        if (
            status
            in ASSERTIVE_PAIN[
                dimension
            ]
            and not refs
        ):
            raise ValueError(
                f"{dimension} status {status} "
                "asserts pain but cites no evidence."
            )


# =========================================================
# EVIDENCE QUALITY FOR PAIN CLAIM
# =========================================================

STATUS_PRIORITY = {
    "VERIFIED": 4,
    "CORROBORATED": 3,
    "UNVERIFIED": 2,
    "CONFLICTING": 1,
}


def strongest_ref_status(
    refs: list[str],
    catalog: dict,
) -> str:

    statuses = [
        catalog[ref][
            "evidence_status"
        ]
        for ref in refs
        if ref in catalog
    ]

    if not statuses:
        return "UNVERIFIED"

    return max(
        statuses,
        key=lambda status: (
            STATUS_PRIORITY.get(
                status,
                0,
            )
        ),
    )


# =========================================================
# DETERMINISTIC COMMERCIAL SCORING
# =========================================================

def score_dimension(
    dimension: str,
    exposure_score: int,
    maximum: int,
    classification: dict,
    catalog: dict,
) -> dict:

    status = str(
        classification.get(
            "status",
            "UNKNOWN",
        )
    ).upper()

    refs = classification.get(
        "evidence_refs",
        [],
    )

    if dimension == "hiring":
        factor = HIRING_FACTORS[
            status
        ]

    elif dimension == "deployment":
        factor = DEPLOYMENT_FACTORS[
            status
        ]

    elif dimension == "roi":
        factor = ROI_FACTORS[
            status
        ]

    else:
        raise ValueError(
            f"Unknown dimension: "
            f"{dimension}"
        )

    quality_status = (
        strongest_ref_status(
            refs,
            catalog,
        )
        if refs
        else None
    )

    quality_factor = 1.0

    scoring_status = status

    if status in ASSERTIVE_PAIN[
        dimension
    ]:

        quality_factor = (
            EVIDENCE_QUALITY_FACTORS.get(
                quality_status
                or "UNVERIFIED",
                0.40,
            )
        )

    # -----------------------------------------------------
    # Evidence symmetry:
    #
    # Weak evidence cannot establish pain, but it also
    # cannot establish a healthy / successful state that
    # suppresses commercial opportunity.
    #
    # VERIFIED or CORROBORATED evidence is required before
    # an exculpatory classification may lower the score.
    # -----------------------------------------------------

    if status in EXCULPATORY[
        dimension
    ]:

        quality_rank = (
            STATUS_PRIORITY.get(
                quality_status
                or "UNVERIFIED",
                0,
            )
        )

        corroborated_rank = (
            STATUS_PRIORITY[
                "CORROBORATED"
            ]
        )

        if quality_rank < corroborated_rank:

            scoring_status = "UNKNOWN"

            if dimension == "hiring":
                factor = HIRING_FACTORS[
                    "UNKNOWN"
                ]

            elif dimension == "deployment":
                factor = DEPLOYMENT_FACTORS[
                    "UNKNOWN"
                ]

            elif dimension == "roi":
                factor = ROI_FACTORS[
                    "UNKNOWN"
                ]

    score = round(
        exposure_score
        * factor
        * quality_factor
    )

    score = max(
        0,
        min(
            score,
            maximum,
        ),
    )

    return {
        "score": score,
        "max_score": maximum,
        "exposure_score": (
            exposure_score
        ),
        "classification": status,
        "scoring_classification": (
            scoring_status
        ),
        "opportunity_factor": factor,
        "classification_evidence_status": (
            quality_status
        ),
        "pain_evidence_status": (
            quality_status
        ),
        "pain_evidence_refs": refs,
        "reason": classification.get(
            "reason",
            "",
        ),
    }


def build_commercial_score(
    result: dict,
    classifications: dict,
    catalog: dict,
) -> dict:

    signals = result[
        "signals"
    ]

    hiring_exposure = signals[
        "ai_hiring"
    ]["score"]

    deployment_exposure = signals[
        "ai_deployment"
    ]["score"]

    # ROI opportunity needs proof that AI is actually material.
    # A company can have bad ROI even when positive ROI evidence
    # is absent, so deployment exposure can establish the base.
    roi_exposure = max(
        signals[
            "ai_value_roi"
        ]["score"],
        signals[
            "ai_deployment"
        ]["score"],
    )

    hiring = score_dimension(
        dimension="hiring",
        exposure_score=(
            hiring_exposure
        ),
        maximum=15,
        classification=(
            classifications[
                "hiring"
            ]
        ),
        catalog=catalog,
    )

    deployment = score_dimension(
        dimension="deployment",
        exposure_score=(
            deployment_exposure
        ),
        maximum=20,
        classification=(
            classifications[
                "deployment"
            ]
        ),
        catalog=catalog,
    )

    roi = score_dimension(
        dimension="roi",
        exposure_score=(
            roi_exposure
        ),
        maximum=20,
        classification=(
            classifications[
                "roi"
            ]
        ),
        catalog=catalog,
    )

    org = {
        "score": signals[
            "organisational_fit"
        ]["score"],
        "max_score": signals[
            "organisational_fit"
        ]["max_score"],
        "reason": (
            signals[
                "organisational_fit"
            ]["reason"]
        ),
        "evidence_status": (
            signals[
                "organisational_fit"
            ]["evidence_status"]
        ),
    }

    commercial_signals = {
        "hiring_opportunity": hiring,
        "deployment_opportunity": (
            deployment
        ),
        "roi_opportunity": roi,
        "organisational_fit": org,
    }

    pain_signal_keys = [
        "hiring_opportunity",
        "deployment_opportunity",
        "roi_opportunity",
    ]

    pain_score = sum(
        commercial_signals[key]["score"]
        for key in pain_signal_keys
    )

    pain_max_score = sum(
        commercial_signals[key]["max_score"]
        for key in pain_signal_keys
    )

    proven_pain = (
        pain_score > 0
    )

    # -----------------------------------------------------
    # Commercial qualification gate
    #
    # Organisational Fit is a qualifier, not evidence of
    # commercial pain.
    #
    # A company with no evidenced pain must not receive a
    # positive Commercial Opportunity Score merely because
    # it is large or otherwise a good organisational fit.
    #
    # Pain scores already incorporate exposure, so a final
    # positive opportunity requires both:
    #
    #   meaningful AI exposure
    #   +
    #   evidenced pain
    # -----------------------------------------------------

    maximum = sum(
        item["max_score"]
        for item
        in commercial_signals.values()
    )

    if proven_pain:

        total = (
            pain_score
            + org["score"]
        )

    else:

        total = 0

    return {
        "company": result[
            "company"
        ],
        "commercial_opportunity_score": (
            total
        ),
        "max_score": maximum,
        "pain_opportunity_score": (
            pain_score
        ),
        "pain_opportunity_max_score": (
            pain_max_score
        ),
        "proven_pain": proven_pain,
        "organisational_fit_is_qualifier": True,
        "commercial_score_gate": (
            "Requires evidenced pain"
        ),
        "activity_score": {
            "score": result[
                "score"
            ],
            "max_score": result[
                "max_score"
            ],
        },
        "signals": commercial_signals,
        "classifications": (
            classifications
        ),
        "evidence_catalog": catalog,
    }


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    result = load_prospect_result()

    result_company = (
        result.get(
            "company",
            "",
        ).strip()
    )

    if (
        result_company.lower()
        != COMPANY.lower()
    ):
        raise ValueError(
            "Commercial Opportunity company mismatch: "
            f"expected {COMPANY!r}, "
            f"got {result_company!r}."
        )

    catalog = build_evidence_catalog(
        result
    )

    classifications = (
        classify_commercial_pain(
            company=result[
                "company"
            ],
            catalog=catalog,
        )
    )

    validate_classifications(
        classifications=(
            classifications
        ),
        catalog=catalog,
    )

    output = build_commercial_score(
        result=result,
        classifications=(
            classifications
        ),
        catalog=catalog,
    )

    Path(
        "latest_commercial_opportunity.json"
    ).write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    print(
        "\n"
        + "=" * 68
    )

    print(
        "GRUNDMIND COMMERCIAL "
        "OPPORTUNITY V2"
    )

    print(
        "=" * 68
    )

    print(
        f"\nCompany: "
        f"{output['company']}"
    )

    print(
        "\nExisting activity score: "
        f"{output['activity_score']['score']}/"
        f"{output['activity_score']['max_score']}"
    )

    for key, label in [
        (
            "hiring_opportunity",
            "Hiring Opportunity",
        ),
        (
            "deployment_opportunity",
            "Deployment Opportunity",
        ),
        (
            "roi_opportunity",
            "ROI Opportunity",
        ),
    ]:

        item = output[
            "signals"
        ][key]

        print(
            f"\n{label}: "
            f"{item['score']}/"
            f"{item['max_score']}"
        )

        print(
            "Exposure: "
            f"{item['exposure_score']}"
        )

        print(
            "Classification: "
            f"{item['classification']}"
        )

        if (
            item[
                "scoring_classification"
            ]
            != item[
                "classification"
            ]
        ):

            print(
                "Scoring classification: "
                f"{item['scoring_classification']} "
                "(weak evidence cannot suppress opportunity)"
            )

        print(
            "Classification evidence: "
            f"{item['classification_evidence_status']}"
        )

        print(
            "Reason: "
            f"{item['reason']}"
        )

    org = output[
        "signals"
    ][
        "organisational_fit"
    ]

    print(
        "\nOrganisational Fit: "
        f"{org['score']}/"
        f"{org['max_score']}"
        " (qualification only)"
    )

    print(
        "\nPain Opportunity: "
        f"{output['pain_opportunity_score']}/"
        f"{output['pain_opportunity_max_score']}"
    )

    print(
        "Proven Pain: "
        + (
            "YES"
            if output["proven_pain"]
            else "NO"
        )
    )

    print(
        "\n"
        + "-" * 68
    )

    print(
        "COMMERCIAL OPPORTUNITY SCORE: "
        f"{output['commercial_opportunity_score']}/"
        f"{output['max_score']}"
    )

    print(
        "\nSaved: "
        "latest_commercial_opportunity.json"
    )


if __name__ == "__main__":
    main()
