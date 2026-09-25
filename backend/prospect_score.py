from dataclasses import dataclass
from enum import Enum


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"


class SourceTier(str, Enum):
    A = "A"  # Official company source
    B = "B"  # Established job board / reputable publication
    C = "C"  # Aggregator / mirror
    D = "D"  # Weak or unknown source


@dataclass
class Evidence:
    source_name: str
    source_tier: SourceTier
    status: EvidenceStatus
    finding: str


@dataclass
class SignalScore:
    name: str
    score: int
    max_score: int
    reason: str
    evidence_status: EvidenceStatus


def score_ai_hiring(
    role_title: str,
    role_description: str,
    evidence: Evidence,
) -> SignalScore:

    title = role_title.lower()
    description = role_description.lower()
    combined = f"{title} {description}"

    # -----------------------------------------------------
    # 1. Direct organisational AI roles
    # -----------------------------------------------------

    direct_operational_title_terms = [
        "ai adoption",
        "ai transformation",
        "ai governance",
        "ai enablement",
        "responsible ai",
        "genai transformation",
        "generative ai transformation",
        "copilot",
        "head of ai",
        "chief ai officer",
        "ai program manager",
        "ai programme manager",
    ]

    # -----------------------------------------------------
    # 2. Organisational AI responsibilities inside
    #    a broader role
    # -----------------------------------------------------

    operational_description_terms = [
        "enterprise ai adoption",
        "ai governance program",
        "ai governance programme",
        "ai governance framework",
        "workforce enablement",
        "ai enablement",
        "responsible ai use",
        "ai transformation",
        "ai adoption",
        "ai roi",
        "workflow redesign",
    ]

    # -----------------------------------------------------
    # 3. Technical AI hiring
    # -----------------------------------------------------

    technical_title_terms = [
        "ai/ml",
        "ai engineer",
        "ml engineer",
        "machine learning engineer",
        "ai research engineer",
        "ai researcher",
        "applied ai",
    ]

    # -----------------------------------------------------
    # 4. AI-adjacent responsibilities
    # -----------------------------------------------------

    adjacent_terms = [
        "ai-enabled",
        "ai enabled",
        "ai-powered",
        "ai powered",
        "ai tools",
        "generative ai",
        "genai",
        "machine learning",
    ]

    if any(
        term in title
        for term in direct_operational_title_terms
    ):
        raw_score = 15
        reason = (
            "Role is directly focused on organisational AI adoption, "
            "transformation, governance, enablement, or leadership."
        )

    elif any(
        term in description
        for term in operational_description_terms
    ):
        raw_score = 8
        reason = (
            "Role has meaningful organisational AI adoption, governance, "
            "enablement, or transformation responsibilities, but AI is not "
            "the primary role mandate."
        )

    elif any(
        term in title
        for term in technical_title_terms
    ):
        raw_score = 5
        reason = (
            "Dedicated technical AI/ML hiring is present, but this is "
            "weaker evidence of organisation-wide AI adoption."
        )

    elif any(
        term in combined
        for term in adjacent_terms
    ):
        raw_score = 3
        reason = (
            "Role includes AI-related responsibilities, but provides only "
            "an adjacent or limited AI adoption signal."
        )

    else:
        raw_score = 0
        reason = (
            "No meaningful AI hiring signal relevant to GrundMind "
            "was identified."
        )

    # -----------------------------------------------------
    # Evidence quality limits what we are allowed to claim.
    # -----------------------------------------------------

    if evidence.status == EvidenceStatus.UNVERIFIED:
        raw_score = min(raw_score, 5)
        reason += " Evidence is currently unverified."

    elif evidence.status == EvidenceStatus.CONFLICTING:
        raw_score = min(raw_score, 3)
        reason += " Available sources conflict."

    return SignalScore(
        name="AI Hiring",
        score=raw_score,
        max_score=15,
        reason=reason,
        evidence_status=evidence.status,
    )


def score_organisational_fit(
    employee_count: int,
    knowledge_worker_heavy: bool,
    multi_department: bool,
    evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED,
) -> SignalScore:

    score = 0
    reasons = []

    if employee_count >= 1000:
        score += 5
        reasons.append("Large organisation")
    elif employee_count >= 250:
        score += 3
        reasons.append("Mid-sized organisation")
    else:
        reasons.append("Small organisation")

    if knowledge_worker_heavy:
        score += 3
        reasons.append(
            "substantial knowledge-worker population"
        )

    if multi_department:
        score += 2
        reasons.append(
            "multi-department operating environment"
        )

    return SignalScore(
        name="Organisational Fit",
        score=score,
        max_score=10,
        reason=", ".join(reasons) + ".",
        evidence_status=evidence_status,
    )



def print_score(company: str, signals: list[SignalScore]) -> None:

    total = sum(signal.score for signal in signals)
    total_possible = sum(signal.max_score for signal in signals)

    print(f"\nCompany: {company}")
    print("=" * 60)

    for signal in signals:
        print(f"\n{signal.name}")
        print(f"Score: {signal.score}/{signal.max_score}")
        print(f"Evidence: {signal.evidence_status.value}")
        print(f"Reason: {signal.reason}")

    print("\n" + "-" * 60)
    print(f"CURRENT SCORE: {total}/{total_possible}")


# ---------------------------------------------------------
# TEST CASE: LOGITECH
# ---------------------------------------------------------
if __name__ == "__main__":

    logitech_hiring_evidence = Evidence(
        source_name="Third-party job listings",
        source_tier=SourceTier.B,
        status=EvidenceStatus.CORROBORATED,
        finding=(
            "Current Compensation Director vacancy includes AI-enabled "
            "tools, experimentation, adoption, and measurable impact."
        ),
    )

    ai_hiring = score_ai_hiring(
        role_title="Compensation Director",
        role_description=(
            "Lead compensation strategy using AI-enabled capabilities, "
            "AI tools, analytics, experimentation, adoption and "
            "measurable business impact."
        ),
        evidence=logitech_hiring_evidence,
    )

    organisational_fit = score_organisational_fit(
        employee_count=7000,
        knowledge_worker_heavy=True,
        multi_department=True,
    )

    print_score(
        company="Logitech",
        signals=[
            ai_hiring,
            organisational_fit,
        ],
    )
