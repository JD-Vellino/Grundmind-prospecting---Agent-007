import os

from evidence_store import (
    get_verified_findings,
)

from research_core import (
    research,
    synthesize_research,
    verify_accepted_findings,
)

from company_config import get_company_config


# =========================================================
# CONFIGURATION
# =========================================================

COMPANY_CONFIG = get_company_config(
    os.environ.get(
        "AGENT007_COMPANY",
        "Logitech",
    )
)
COMPANY = COMPANY_CONFIG.name
RESEARCH_IDENTITY = COMPANY_CONFIG.research_identity


# =========================================================
# RESEARCH OBJECTIVES
# =========================================================

# We deliberately use separate bounded objectives rather than one
# giant "find problems" prompt.
#
# This gives the research planner distinct opportunities to find:
# 1. ROI / value pain
# 2. deployment / adoption friction
# 3. governance / transformation remediation
#
# All findings persist into one durable commercial_pain stream.

OBJECTIVES = [
    (
        "ROI / VALUE PAIN",
        (
            f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
            f"Find current or recent public evidence that {COMPANY} has "
            "difficulty proving, measuring, realizing, or achieving "
            "expected business value or financial ROI from INTERNAL AI "
            "investment, deployment, adoption, automation, GenAI, AI "
            "agents, Copilot, or other employee/workflow AI. "
            "Look specifically for explicit statements that AI ROI is "
            "unclear, difficult to prove, below expectations, delayed, "
            "inconsistent, disputed, insufficient, or unsuccessful; "
            "that expected benefits have not materialized; or that AI "
            "projects were reduced, stopped, reconsidered, or criticized "
            "because value was not demonstrated."
        ),
    ),
    (
        "DEPLOYMENT / ADOPTION FRICTION",
        (
            f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
            f"Find current or recent public evidence that {COMPANY} has "
            "experienced problems with INTERNAL AI deployment or adoption. "
            "Look specifically for stalled pilots, failed pilots, low "
            "employee adoption, uneven adoption between teams or functions, "
            "workflow friction, employee resistance, poor output quality, "
            "tool sprawl, rollout delays, inability to scale, abandoned or "
            "rolled-back AI projects, inconsistent use, implementation "
            "difficulty, or operational problems caused by internal AI."
        ),
    ),
    (
        "GOVERNANCE / ENABLEMENT / REMEDIATION",
        (
            f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
            f"Find current or recent public evidence that {COMPANY} has "
            "identified an INTERNAL AI governance, ownership, capability, "
            "training, transformation, change-management, workflow, or "
            "coordination problem that requires remediation. "
            "Look for explicit statements about governance gaps, unclear "
            "ownership, uncontrolled AI use, shadow AI, policy violations, "
            "skills gaps, lack of training, fragmented adoption, weak "
            "processes, inconsistent controls, failed transformation, or "
            "roles/programmes created specifically to fix an identified "
            "AI adoption or value problem."
        ),
    ),
]


# =========================================================
# STRICT VALIDATION BOUNDARY
# =========================================================

PAIN_VALIDATION_RULES = """
The objective is to identify EVIDENCED AI PAIN, FAILURE, FRICTION,
UNDERPERFORMANCE, OR REMEDIATION NEED at the target company.

Accept a finding only when the supplied evidence explicitly establishes
a meaningful problem, deficiency, difficulty, failure, friction, or
corrective response involving INTERNAL AI use.

Potentially relevant evidence includes:

ROI / VALUE
- AI ROI is difficult to prove
- ROI is below expectations
- expected value has not materialized
- benefits are inconsistent
- AI costs outweigh or materially weaken value
- leadership explicitly questions AI returns
- projects are reconsidered because value is unclear
- financial or operational outcomes are disappointing

DEPLOYMENT / ADOPTION
- pilot failed or stalled
- deployment failed to scale
- rollout was delayed because of problems
- adoption is explicitly low
- adoption is explicitly uneven
- employees resist or avoid the AI system
- workflow friction is explicitly reported
- AI output quality creates operational problems
- tools were rolled back, abandoned, or discontinued
- inconsistent use creates an identified problem

GOVERNANCE / ENABLEMENT / REMEDIATION
- explicit governance gap
- uncontrolled or shadow AI is identified as a problem
- unclear ownership is identified as a problem
- explicit capability or skills gap
- insufficient AI training is identified as a problem
- fragmented adoption is explicitly identified
- controls are explicitly inadequate or inconsistent
- a transformation, governance, enablement, or remediation programme
  is explicitly created to address an identified problem


STRICT NON-INFERENCE RULES:

The following are NOT pain evidence by themselves:

- AI investment
- AI deployment
- broad AI deployment
- AI hiring
- an AI Governance Specialist vacancy
- creation of an AI governance team
- a Chief AI Officer
- training programmes
- adoption programmes
- transformation programmes
- AI strategy
- leadership interest in AI
- AI experimentation
- successful operational metrics
- vendor success stories
- absence of public ROI evidence
- absence of financial ROI numbers
- large organisational scale
- multiple departments
- rapid AI growth
- large numbers of AI agents
- generic statements that AI is challenging
- generic industry commentary about AI risks
- statements about what companies in general struggle with

A governance, adoption, transformation, or enablement initiative is
acceptable only when the evidence explicitly connects it to a concrete
problem or deficiency at the target company.

A job vacancy is acceptable only when the evidence explicitly states
that the role is intended to address an identified AI problem,
deficiency, failure, or remediation need.

Do NOT reason:

"No enterprise ROI evidence was found"
therefore
"The target company has an ROI problem."

Do NOT reason:

"The target company is hiring in AI governance"
therefore
"The target company has a governance failure."

Do NOT reason:

"The target company has thousands of AI agents"
therefore
"The target company has adoption or governance problems."

The evidence must establish the negative condition or remediation need.

The objective concerns INTERNAL AI use and adoption.

Reject:

- customer-facing AI product problems unless they independently
  establish an internal AI adoption problem
- customer complaints about the target company's products
- ordinary product defects
- general business underperformance unrelated to internal AI
- unrelated restructuring
- unrelated layoffs
- generic technology transformation problems
- speculative analyst conclusions
- statements belonging to another company
- unsupported causal connections
- duplicated findings
- historical problems that are clearly resolved unless current
  relevance is explicitly established

Preserve uncertainty and the exact scope of the evidence.

Do not strengthen:
"some employees reported difficulty"
into
"company-wide adoption failure."

Do not strengthen:
"ROI measurement remains under development"
into
"AI ROI has failed."

False negatives are strongly preferable to false positives.
"""


# =========================================================
# RUN RESEARCH
# =========================================================

print(
    "\n"
    + "=" * 68
)

print(
    "COMMERCIAL PAIN RESEARCH"
)

print(
    "=" * 68
)

for objective_name, objective in OBJECTIVES:

    print(
        "\n\n"
        + "=" * 68
    )

    print(
        objective_name
    )

    print(
        "=" * 68
    )

    research_result = research(
        company=COMPANY,
        objective=objective,
        max_searches=2,
    )

    validated = synthesize_research(
        company=COMPANY,
        objective=objective,
        research_result=research_result,
        validation_rules=(
            PAIN_VALIDATION_RULES
        ),
    )

    verified = verify_accepted_findings(
        validated,
        signal="commercial_pain",
    )

    new_verified = verified.get(
        "verified_findings",
        [],
    )

    print(
        "\nNew source-verified pain findings "
        f"from this objective: "
        f"{len(new_verified)}"
    )


# =========================================================
# DURABLE RESULT
# =========================================================

durable_findings = get_verified_findings(
    company=COMPANY,
    signal="commercial_pain",
)

print(
    "\n\n"
    + "=" * 68
)

print(
    "DURABLE COMMERCIAL PAIN EVIDENCE"
)

print(
    "=" * 68
)

print(
    f"\nEstablished findings: "
    f"{len(durable_findings)}"
)

for index, finding in enumerate(
    durable_findings,
    start=1,
):

    print(
        f"\n{index}. "
        f"{finding.get('claim', '')}"
    )

    supported_urls = []

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

        if source_url:
            supported_urls.append(
                source_url
            )

    for source_url in dict.fromkeys(
        supported_urls
    ):

        print(
            f"   - {source_url}"
        )
