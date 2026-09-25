import json
import os

from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

from research_core import (
    clean_json,
    research,
    synthesize_research,
    verify_accepted_findings,
)

from deployment_score import (
    DeploymentEvidence,
    score_ai_deployment,
)

from prospect_score import (
    Evidence,
    EvidenceStatus,
    SourceTier,
)

from evidence_quality import (
    classify_evidence_status,
    classify_source_tier,
)

from company_config import get_company_config


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


# =========================================================
# COMPANY CONFIGURATION
# =========================================================

COMPANY_CONFIG = get_company_config(
    os.environ.get(
        "AGENT007_COMPANY",
        "Logitech",
    )
)
COMPANY = COMPANY_CONFIG.name
RESEARCH_IDENTITY = COMPANY_CONFIG.research_identity

_SOURCE_POLICY = COMPANY_CONFIG.policy(
    "ai_deployment"
)

OFFICIAL_DOMAINS = list(
    _SOURCE_POLICY.official_domains
)

OFFICIAL_SOURCE_PREFIXES = list(
    _SOURCE_POLICY.official_source_prefixes
)


# =========================================================
# RESEARCH OBJECTIVE
# =========================================================

DEPLOYMENT_OBJECTIVE = (
    f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
    f"Find current or recent public evidence of meaningful AI activity "
    f"at {COMPANY}. Search for internal AI deployment AND broader AI "
    "activity such as AI embedded in products or customer-facing "
    "services, AI assistants or platforms, AI-related acquisitions, "
    "and major AI technology partnerships or integrations. "
    "Preserve whether evidence concerns internal deployment, "
    "product/customer-facing AI, or strategic AI exposure. "
    "Do not infer internal employee adoption from product AI."
)


# =========================================================
# DEPLOYMENT-SPECIFIC VALIDATION RULES
# =========================================================

DEPLOYMENT_VALIDATION_RULES = """
Accept findings when they establish meaningful attributable AI activity
by the target company.

Evidence may establish:

- INTERNAL AI DEPLOYMENT
- PRODUCT / CUSTOMER-FACING AI
- STRATEGIC AI EXPOSURE

Only INTERNAL AI DEPLOYMENT may establish PILOT, ACTIVE, or SCALED
internal deployment.

Product/customer-facing AI and strategic AI exposure should still be
retained as relevant AI evidence, but must not be treated as proof of
internal employee adoption.

Relevant deployment evidence includes:

- Microsoft Copilot deployed to employees
- ChatGPT Enterprise or Claude deployed internally
- internal GenAI assistants
- enterprise AI platforms used by employees
- AI agents operating in internal workflows
- AI embedded into business processes
- AI being used in a specific department or business function
- production AI workflows
- multi-department AI use
- broad employee AI adoption
- large internal AI pilots
- company-wide or enterprise-scale AI deployment
- explicit employee, team, workflow, agent, or usage counts

A finding must establish more than interest, strategy, capability,
governance, or intention.

Surveys, questionnaires, or measurement of employee AI usage do not
by themselves establish deployment.

Accept survey evidence as deployment only when the reported results
independently establish that employees, teams, functions, or workflows
are actually using deployed AI systems.

A company asking employees whether they use AI is not itself evidence
that the company deployed AI.

IMPORTANT DEPLOYMENT BOUNDARY:

AI governance is NOT deployment by itself.

An AI governance board, committee, policy, framework, ethics programme,
responsible-AI initiative, or executive discussion does not establish
that AI is actually deployed in operational work.

AI leadership is NOT deployment by itself.

A Chief AI Officer, Head of AI, AI team, transformation programme,
or leadership statement does not establish deployment unless the
evidence independently shows actual internal AI use.

AI hiring is NOT deployment.

A vacancy or employee role may indicate organisational interest but
does not prove AI is being used operationally.

Customer-facing AI products are NOT internal deployment.

However, retain specific attributable evidence of:

- AI embedded in products or services
- customer-facing AI assistants
- AI-enabled platforms operated by the target company
- AI control towers or decision-support systems
- significant AI-related acquisitions
- major AI technology partnerships or integrations

These establish PRODUCT / CUSTOMER-FACING AI or STRATEGIC AI EXPOSURE.
They do NOT establish internal deployment unless separate evidence
shows employees, teams, departments, workflows, or business processes
are actually using AI internally.

Still reject:

- generic product marketing with no specific AI capability
- generic AI strategy statements
- executive commentary without concrete AI activity
- AI governance without operational activity
- AI hiring without operational activity
- speculative or inferred deployment
- deployment belonging to another company

PILOT evidence must establish an actual limited trial, experiment,
proof of concept, or controlled rollout.

ACTIVE evidence must establish actual use in a real team, function,
department, workflow, or business process.

SCALED evidence must establish broad organisational use such as:

- multiple departments
- multiple business functions
- thousands of employees
- broad workforce use
- company-wide rollout
- enterprise-wide deployment
- substantial operational scale across the organisation

Do not infer SCALED merely because an AI programme sounds important.

Do not infer deployment from a strategy statement.

Do not infer current deployment from clearly historical or discontinued
activity.

For accepted findings, phrase claims conservatively and preserve the
actual deployment scope supported by the evidence.

False negatives are preferable to false positives.
"""


# =========================================================
# PRIORITIES
# =========================================================

TIER_PRIORITY = {
    SourceTier.A: 1,
    SourceTier.B: 2,
    SourceTier.C: 3,
    SourceTier.D: 4,
}

STATUS_PRIORITY = {
    EvidenceStatus.VERIFIED: 4,
    EvidenceStatus.CORROBORATED: 3,
    EvidenceStatus.UNVERIFIED: 2,
    EvidenceStatus.CONFLICTING: 1,
}

DEPLOYMENT_STATUS_PRIORITY = {
    "SCALED": 3,
    "ACTIVE": 2,
    "PILOT": 1,
    "UNKNOWN": 0,
}


# =========================================================
# DEPLOYMENT CLASSIFIER
# =========================================================

def classify_deployment_findings(
    company: str,
    findings: list[dict],
) -> list[dict]:

    if not findings:
        return []

    current_date = datetime.now(
        timezone.utc
    ).date().isoformat()

    classifier_input = []

    for index, finding in enumerate(
        findings
    ):

        classifier_input.append(
            {
                "evidence_index": index,
                "claim": finding.get(
                    "claim",
                    "",
                ),
                "evidence_detail": finding.get(
                    "evidence_detail",
                    "",
                ),
                "source_verifications": finding.get(
                    "source_verifications",
                    [],
                ),
                "verified_at": finding.get(
                    "verified_at",
                ),
            }
        )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI deployment evidence classification agent. "
                    "Do not perform research. "
                    "Do not use outside knowledge. "
                    "The supplied findings have already passed source fetching "
                    "and claim verification. "
                    "Classify only what the supplied evidence establishes. "
                    "Do not strengthen deployment scope. "
                    "Do not turn strategy, governance, hiring, leadership, "
                    "or product AI into internal deployment. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Target company:
{company}

Current date:
{current_date}

Use only the supplied established evidence.

Classify each finding into exactly one deployment status:

PILOT
= evidence establishes a limited experiment, trial, proof of concept,
  or controlled rollout.

ACTIVE
= evidence establishes actual internal AI use in a real team,
  department, function, workflow, or operational process.

SCALED
= evidence establishes broad internal use across multiple functions,
  multiple departments, a large employee population, company-wide use,
  or enterprise-scale deployment.

UNKNOWN
= evidence does not establish actual internal deployment strongly
  enough for one of the above categories.


STRICT RULES:

- AI strategy alone = UNKNOWN.
- AI leadership alone = UNKNOWN.
- AI governance alone = UNKNOWN.
- An AI governance board or committee = UNKNOWN.
- AI hiring alone = UNKNOWN.
- AI products sold to customers = UNKNOWN.
- AI product features = UNKNOWN.
- Future intentions or plans = UNKNOWN.
- Research or engineering activity alone = UNKNOWN.

Do not infer SCALED because a deployment sounds sophisticated.

Examples:

"AI is important to our strategy"
→ UNKNOWN

"We established an AI governance board"
→ UNKNOWN

"We are hiring an AI Governance Specialist"
→ UNKNOWN

"Finance uses an AI system in accounts payable"
→ ACTIVE

"We are piloting Copilot with 100 employees"
→ PILOT

"AI tools are deployed across multiple departments"
→ SCALED


For each finding return:

- evidence_index
- deployment_type
- scope
- description
- deployment_status

The scope and description must preserve the actual evidence rather
than exaggerating deployment scale.

Preserve evidence_index exactly.


Return exactly:

{{
  "deployments": [
    {{
      "evidence_index": 0,
      "deployment_type": "",
      "scope": "",
      "description": "",
      "deployment_status": "PILOT|ACTIVE|SCALED|UNKNOWN"
    }}
  ]
}}


ESTABLISHED DEPLOYMENT EVIDENCE:

{json.dumps(classifier_input, indent=2)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=2048,
        timeout=120,
        extra_body={
            "thinking": {
                "type": "disabled"
            }
        },
    )

    data = clean_json(
        response.choices[0].message.content or ""
    )

    return data.get(
        "deployments",
        [],
    )


# =========================================================
# SUPPORTED SOURCE HELPERS
# =========================================================

def get_supported_source_urls(
    finding: dict,
) -> list[str]:

    urls = []

    for verification in finding.get(
        "source_verifications",
        [],
    ):

        if (
            verification.get(
                "verification_status"
            )
            == "SUPPORTED"
        ):

            source_url = verification.get(
                "source_url"
            )

            if source_url:
                urls.append(
                    source_url
                )

    return list(
        dict.fromkeys(
            urls
        )
    )


def get_supported_source_names(
    finding: dict,
    supported_urls: list[str],
) -> list[str]:

    names = []

    for source in finding.get(
        "sources",
        [],
    ):

        if source.get(
            "source_url"
        ) not in supported_urls:
            continue

        names.append(
            source.get(
                "source_name",
                "Unknown source",
            )
        )

    return names


# =========================================================
# 1. RESEARCH
# =========================================================

research_result = research(
    company=COMPANY,
    objective=DEPLOYMENT_OBJECTIVE,
    max_searches=3,
)


# =========================================================
# 2. SEMANTIC VALIDATION
# =========================================================

validated = synthesize_research(
    company=COMPANY,
    objective=DEPLOYMENT_OBJECTIVE,
    research_result=research_result,
    validation_rules=DEPLOYMENT_VALIDATION_RULES,
)


# =========================================================
# 3. SOURCE VERIFICATION + PERSISTENCE
# =========================================================

verified = verify_accepted_findings(
    validated,
    signal="ai_deployment",
)


durable_findings = verified.get(
    "stored_verified_findings",
    [],
)

print(
    f"\nEstablished durable deployment evidence: "
    f"{len(durable_findings)}"
)


# =========================================================
# 4. CLASSIFY ESTABLISHED DEPLOYMENT EVIDENCE
# =========================================================

classified_deployments = (
    classify_deployment_findings(
        company=COMPANY,
        findings=durable_findings,
    )
)

deployment_by_index = {
    deployment["evidence_index"]: deployment
    for deployment in classified_deployments
    if "evidence_index" in deployment
}


# =========================================================
# 5. DETERMINISTIC EVIDENCE QUALITY + SCORE
# =========================================================

deployment_results = []


print(
    "\nDEPLOYMENT-BY-DEPLOYMENT EVIDENCE CHECK"
)


for index, finding in enumerate(
    durable_findings
):

    deployment = deployment_by_index.get(
        index
    )

    if not deployment:
        continue

    deployment_type = deployment.get(
        "deployment_type",
        "Unknown deployment",
    )

    deployment_status = deployment.get(
        "deployment_status",
        "UNKNOWN",
    ).upper()

    print(
        f"\nDeployment: {deployment_type}"
    )

    print(
        f"Status: {deployment_status}"
    )

    # Unknown AI activity is not enough
    # to score Deployment.
    if deployment_status == "UNKNOWN":

        print(
            "Result: SKIPPED - "
            "deployment not established"
        )

        continue

    supported_urls = get_supported_source_urls(
        finding
    )

    if not supported_urls:

        print(
            "Result: SKIPPED - "
            "no supported source"
        )

        continue

    evidence_status = classify_evidence_status(
        urls=supported_urls,
        official_domains=OFFICIAL_DOMAINS,
        official_source_prefixes=(
            OFFICIAL_SOURCE_PREFIXES
        ),
    )

    source_tiers = [
        classify_source_tier(
            url=url,
            official_domains=OFFICIAL_DOMAINS,
            official_source_prefixes=(
                OFFICIAL_SOURCE_PREFIXES
            ),
        )
        for url in supported_urls
    ]

    best_source_tier = min(
        source_tiers,
        key=lambda tier: (
            TIER_PRIORITY[tier]
        ),
    )

    source_names = get_supported_source_names(
        finding,
        supported_urls,
    )

    for url, tier in zip(
        supported_urls,
        source_tiers,
    ):

        print(
            f"  - {tier.value} | {url}"
        )

    print(
        f"Evidence status: "
        f"{evidence_status.value}"
    )

    evidence = Evidence(
        source_name=(
            ", ".join(source_names)
            or "Verified public source"
        ),
        source_tier=best_source_tier,
        status=evidence_status,
        finding=finding.get(
            "claim",
            "",
        ),
    )

    deployment_evidence = DeploymentEvidence(
        deployment_status=deployment_status,
        scope=deployment.get(
            "scope",
            "",
        ),
        description=deployment.get(
            "description",
            "",
        ),
        evidence=evidence,
    )

    signal_score = score_ai_deployment(
        deployment_evidence
    )

    print(
        f"Deployment score: "
        f"{signal_score.score}/"
        f"{signal_score.max_score}"
    )

    deployment_results.append(
        {
            "deployment": deployment,
            "finding": finding,
            "score": signal_score,
            "evidence": evidence,
        }
    )


# =========================================================
# 6. SELECT STRONGEST DEFENSIBLE DEPLOYMENT SIGNAL
# =========================================================

if deployment_results:

    best_deployment = max(
        deployment_results,
        key=lambda item: (
            item["score"].score,
            STATUS_PRIORITY[
                item["evidence"].status
            ],
            -TIER_PRIORITY[
                item["evidence"].source_tier
            ],
            DEPLOYMENT_STATUS_PRIORITY.get(
                item["deployment"].get(
                    "deployment_status",
                    "UNKNOWN",
                ).upper(),
                0,
            ),
        ),
    )

    deployment_score = (
        best_deployment["score"]
    )

    print(
        "\nSELECTED AI DEPLOYMENT SIGNAL"
    )

    print(
        f"Deployment: "
        f"{best_deployment['deployment']['deployment_type']}"
    )

    print(
        f"Status: "
        f"{best_deployment['deployment']['deployment_status']}"
    )

    print(
        f"Evidence: "
        f"{best_deployment['evidence'].status.value}"
    )

    print(
        f"Score: "
        f"{deployment_score.score}/"
        f"{deployment_score.max_score}"
    )

else:

    evidence = Evidence(
        source_name=(
            "No qualifying evidence found"
        ),
        source_tier=SourceTier.D,
        status=EvidenceStatus.UNVERIFIED,
        finding=(
            "No meaningful internal AI deployment "
            "evidence was established."
        ),
    )

    deployment_evidence = (

        DeploymentEvidence(
            deployment_status="UNKNOWN",
            scope="",
            description="",
            evidence=evidence,
        )
    )

    deployment_score = score_ai_deployment(
        deployment_evidence
    )


# =========================================================
# FINAL RESULT
# =========================================================

print(
    "\n\nDETERMINISTIC AI DEPLOYMENT SCORE"
)

print(
    f"Company: {COMPANY}"
)

print(
    f"AI Deployment: "
    f"{deployment_score.score}/"
    f"{deployment_score.max_score}"
)

print(
    f"Evidence: "
    f"{deployment_score.evidence_status.value}"
)

print(
    f"Reason: "
    f"{deployment_score.reason}"
)