from dataclasses import dataclass

from prospect_score import (
    Evidence,
    EvidenceStatus,
    SignalScore,
)


@dataclass
class DeploymentEvidence:
    deployment_status: str
    scope: str
    description: str
    evidence: Evidence


def score_ai_deployment(
    deployment: DeploymentEvidence,
) -> SignalScore:

    status = deployment.deployment_status.upper()

    if status == "SCALED":
        raw_score = 20
        reason = (
            "Evidence establishes broad or enterprise-scale "
            "internal AI deployment."
        )

    elif status == "ACTIVE":
        raw_score = 10
        reason = (
            "Evidence establishes active internal AI use within "
            "a team, function, department, or workflow."
        )

    elif status == "PILOT":
        raw_score = 5
        reason = (
            "Evidence establishes a limited AI pilot, experiment, "
            "trial, or controlled rollout."
        )

    else:
        raw_score = 0
        reason = (
            "No material internal AI deployment was established."
        )

    if deployment.evidence.status == EvidenceStatus.UNVERIFIED:
        raw_score = min(raw_score, 7)
        reason += " Evidence is currently unverified."

    elif deployment.evidence.status == EvidenceStatus.CONFLICTING:
        raw_score = min(raw_score, 5)
        reason += " Available sources conflict."

    return SignalScore(
        name="AI Deployment",
        score=raw_score,
        max_score=20,
        reason=reason,
        evidence_status=deployment.evidence.status,
    )