from dataclasses import dataclass

from prospect_score import (
    Evidence,
    EvidenceStatus,
    SignalScore,
)


@dataclass
class ROIValueEvidence:
    value_status: str
    description: str
    evidence: Evidence


def score_ai_value(
    value: ROIValueEvidence,
) -> SignalScore:

    status = value.value_status.upper()

    # -----------------------------------------------------
    # Deterministic value / ROI scale
    # -----------------------------------------------------

    if status == "EXPLICIT_ROI":
        raw_score = 20
        reason = (
            "Evidence shows explicit measurement or management of "
            "AI ROI, financial value, or benefits realization."
        )

    elif status == "MEASURED_VALUE":
        raw_score = 15
        reason = (
            "Evidence shows AI business impact or value is being "
            "measured with concrete outcomes or metrics."
        )

    elif status == "OPERATIONAL_METRICS":
        raw_score = 10
        reason = (
            "Evidence shows AI productivity, efficiency, workflow, "
            "adoption, or operational impact is being measured."
        )

    elif status == "ASPIRATIONAL":
        raw_score = 5
        reason = (
            "The company explicitly wants to measure AI value or impact, "
            "but evidence of an established measurement approach is limited."
        )

    else:
        raw_score = 0
        reason = (
            "No meaningful evidence of AI value or ROI measurement "
            "was established."
        )

    # -----------------------------------------------------
    # Evidence-quality caps
    # -----------------------------------------------------

    if value.evidence.status == EvidenceStatus.UNVERIFIED:
        raw_score = min(raw_score, 7)
        reason += " Evidence is currently unverified."

    elif value.evidence.status == EvidenceStatus.CONFLICTING:
        raw_score = min(raw_score, 5)
        reason += " Available sources conflict."

    return SignalScore(
        name="AI Value / ROI",
        score=raw_score,
        max_score=20,
        reason=reason,
        evidence_status=value.evidence.status,
    )


if __name__ == "__main__":

    test_evidence = Evidence(
        source_name="Test source",
        source_tier=None,
        status=EvidenceStatus.VERIFIED,
        finding=(
            "Company tracks AI ROI and benefits realization "
            "across enterprise workflows."
        ),
    )

    value = ROIValueEvidence(
        value_status="EXPLICIT_ROI",
        description=(
            "Leadership measures AI ROI and business value "
            "from workflow redesign."
        ),
        evidence=test_evidence,
    )

    result = score_ai_value(value)

    print("\nAI Value / ROI")
    print(f"Score: {result.score}/{result.max_score}")
    print(f"Evidence: {result.evidence_status.value}")
    print(f"Reason: {result.reason}")
