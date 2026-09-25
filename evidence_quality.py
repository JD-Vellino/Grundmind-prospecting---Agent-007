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


# ---------------------------------------------------------
# Source type
#
# Independent of the tier: says WHAT KIND of source it is,
# so the brief can attribute it honestly and scoring can
# weight it. Academic theses and vendor marketing can be
# confirmed word-for-word and still not be current company
# facts.
# ---------------------------------------------------------

SOURCE_TYPE_COMPANY = "COMPANY"
SOURCE_TYPE_PRESS = "PRESS"
SOURCE_TYPE_JOB_POSTING = "JOB_POSTING"
SOURCE_TYPE_ACADEMIC = "ACADEMIC"
SOURCE_TYPE_VENDOR = "VENDOR_CONTENT"

# Weaker source types: confirmed, but indirect.
INDIRECT_SOURCE_TYPES = {
    SOURCE_TYPE_ACADEMIC,
    SOURCE_TYPE_VENDOR,
}

SOURCE_TYPE_PRIORITY = {
    SOURCE_TYPE_COMPANY: 5,
    SOURCE_TYPE_PRESS: 4,
    SOURCE_TYPE_JOB_POSTING: 3,
    SOURCE_TYPE_VENDOR: 2,
    SOURCE_TYPE_ACADEMIC: 1,
}

ACADEMIC_DOMAINS = {
    "diva-portal.org",
    "lup.lub.lu.se",
    "theseus.fi",
    "essay.utwente.nl",
    "arxiv.org",
    "ssrn.com",
    "researchgate.net",
    "semanticscholar.org",
    "core.ac.uk",
    "hal.science",
    "zenodo.org",
}

ACADEMIC_MARKERS = (
    "student-papers",
    "thesis",
    "theses",
    "dissertation",
    "dspace",
    "eprints",
    "repository",
    "urn:nbn",
    "diva2:",
)

VENDOR_PATH_MARKERS = (
    "case-study",
    "case-studies",
    "casestudy",
    "customer-story",
    "customer-stories",
    "success-story",
    "success-stories",
    "/customers/",
    "/customer/",
    "/clients/",
)

JOB_PATH_MARKERS = (
    "/jobs/",
    "/job/",
    "/work/ad/",
    "/vacancy",
    "/vacancies",
    "/careers/",
)


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


def classify_source_type(
    url: str,
    official_domains: list[str],
    official_source_prefixes: list[str] | None = None,
) -> str:

    tier = classify_source_tier(
        url=url,
        official_domains=official_domains,
        official_source_prefixes=official_source_prefixes,
    )

    if tier == SourceTier.A:
        return SOURCE_TYPE_COMPANY

    hostname = hostname_from_url(url)
    lowered = url.lower()

    if (
        any(
            domain_matches(hostname, domain)
            for domain in ACADEMIC_DOMAINS
        )
        or any(
            marker in lowered
            for marker in ACADEMIC_MARKERS
        )
    ):
        return SOURCE_TYPE_ACADEMIC

    if tier in (SourceTier.B, SourceTier.C) or any(
        marker in lowered
        for marker in JOB_PATH_MARKERS
    ):
        return SOURCE_TYPE_JOB_POSTING

    if any(
        marker in lowered
        for marker in VENDOR_PATH_MARKERS
    ):
        return SOURCE_TYPE_VENDOR

    return SOURCE_TYPE_PRESS


def strongest_source_type(
    urls: list[str],
    official_domains: list[str],
    official_source_prefixes: list[str] | None = None,
) -> str | None:

    types = [
        classify_source_type(
            url=url,
            official_domains=official_domains,
            official_source_prefixes=official_source_prefixes,
        )
        for url in urls
        if hostname_from_url(url)
    ]

    if not types:
        return None

    return max(
        types,
        key=lambda source_type: (
            SOURCE_TYPE_PRIORITY[source_type]
        ),
    )


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

        source_type = classify_source_type(
            url=url,
            official_domains=official_domains,
            official_source_prefixes=official_source_prefixes,
        )

        unique_sources[hostname] = (
            tier,
            source_type,
        )

    sources = list(
        unique_sources.values()
    )

    # One official company source is enough.
    if any(
        tier == SourceTier.A
        for tier, _ in sources
    ):
        return EvidenceStatus.VERIFIED

    # Every caller passes only URLs whose fetched text was
    # checked by verify_claim.py and returned SUPPORTED.
    # A claim confirmed in an independent source (press,
    # trade media, job postings) is therefore corroborated.
    #
    # Academic theses and vendor case studies stay
    # UNVERIFIED for scoring: confirmed in the text, but
    # indirect and possibly dated. account_brief.py may
    # still use them with explicit attribution.
    # Low-quality aggregators (Tier C) alone stay unverified.
    if any(
        tier in (SourceTier.B, SourceTier.D)
        and source_type not in INDIRECT_SOURCE_TYPES
        for tier, source_type in sources
    ):
        return EvidenceStatus.CORROBORATED

    return EvidenceStatus.UNVERIFIED
