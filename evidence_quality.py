from urllib.parse import urlparse

from prospect_score import EvidenceStatus, SourceTier


TIER_B_DOMAINS = {
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "builtin.com",
    "builtinsf.com",
}

TIER_C_DOMAINS = {
    "cake.me",
    "bebee.com",
}


def hostname_from_url(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.lower().removeprefix("www.")


def domain_matches(
    hostname: str,
    domain: str,
) -> bool:
    return (
        hostname == domain
        or hostname.endswith("." + domain)
    )


def official_prefix_matches(
    url: str,
    prefix: str,
) -> bool:

    url_parts = urlparse(url)
    prefix_parts = urlparse(prefix)

    url_hostname = (
        url_parts.hostname or ""
    ).lower()

    prefix_hostname = (
        prefix_parts.hostname or ""
    ).lower()

    if url_hostname != prefix_hostname:
        return False

    return url_parts.path.startswith(
        prefix_parts.path
    )


def classify_source_tier(
    url: str,
    official_domains: list[str],
    official_source_prefixes: list[str] | None = None,
) -> SourceTier:

    hostname = hostname_from_url(url)

    if any(
        domain_matches(hostname, domain)
        for domain in official_domains
    ):
        return SourceTier.A

    if official_source_prefixes and any(
        official_prefix_matches(
            url,
            prefix,
        )
        for prefix in official_source_prefixes
    ):
        return SourceTier.A

    if any(
        domain_matches(hostname, domain)
        for domain in TIER_B_DOMAINS
    ):
        return SourceTier.B

    if any(
        domain_matches(hostname, domain)
        for domain in TIER_C_DOMAINS
    ):
        return SourceTier.C

    return SourceTier.D


def status_for_single_source(
    tier: SourceTier,
) -> EvidenceStatus:

    if tier == SourceTier.A:
        return EvidenceStatus.VERIFIED

    return EvidenceStatus.UNVERIFIED


def classify_evidence_status(
    urls: list[str],
    official_domains: list[str],
    official_source_prefixes: list[str] | None = None,
) -> EvidenceStatus:

    unique_sources = {}

    for url in urls:

        hostname = hostname_from_url(url)

        if not hostname:
            continue

        tier = classify_source_tier(
            url=url,
            official_domains=official_domains,
            official_source_prefixes=official_source_prefixes,
        )

        unique_sources[hostname] = tier

    tiers = list(
        unique_sources.values()
    )

    # One official company source is enough.
    if SourceTier.A in tiers:
        return EvidenceStatus.VERIFIED

    # Conservative rule:
    # require at least two independent Tier B sources.
    tier_b_count = sum(
        1
        for tier in tiers
        if tier == SourceTier.B
    )

    if tier_b_count >= 2:
        return EvidenceStatus.CORROBORATED

    return EvidenceStatus.UNVERIFIED