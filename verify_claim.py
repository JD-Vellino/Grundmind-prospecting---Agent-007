import json
import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI

from fetch_source import fetch_source_text


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


# =========================================================
# TEXT HELPERS
# =========================================================

STOP_WORDS = {
    "the", "and", "that", "this", "with", "from", "into",
    "through", "company", "implemented", "increased",
    "resulted", "results", "their", "they", "were", "was",
    "are", "for", "its", "has", "have", "had", "more",
    "than", "using", "used", "use", "over", "under",
}


def claim_terms(claim: str) -> list[str]:
    words = re.findall(
        r"[A-Za-z][A-Za-z0-9_-]{2,}",
        claim.lower(),
    )

    terms = []

    for word in words:
        if word not in STOP_WORDS and word not in terms:
            terms.append(word)

    return terms


def numeric_terms(claim: str) -> list[str]:
    """
    Extract numbers and percentages from the claim.

    Numerical claims deserve extra scrutiny.
    """

    return re.findall(
        r"(?:[$€£CHF\s]*)?\d+(?:\.\d+)?%?",
        claim,
        flags=re.IGNORECASE,
    )


def chunk_text(
    text: str,
    chunk_size: int = 5000,
    overlap: int = 500,
) -> list[str]:

    if len(text) <= chunk_size:
        return [text]

    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size

        chunks.append(
            text[start:end]
        )

        start += chunk_size - overlap

    return chunks


def rank_chunks(
    text: str,
    claim: str,
    max_chunks: int = 6,
) -> list[str]:

    chunks = chunk_text(text)

    terms = claim_terms(claim)
    numbers = numeric_terms(claim)

    ranked = []

    for index, chunk in enumerate(chunks):

        lower = chunk.lower()

        word_score = sum(
            1
            for term in terms
            if term in lower
        )

        number_score = sum(
            3
            for number in numbers
            if number.strip().lower() in lower
        )

        score = (
            word_score
            + number_score
        )

        ranked.append(
            (
                score,
                index,
                chunk,
            )
        )

    ranked.sort(
        key=lambda item: (
            item[0],
            -item[1],
        ),
        reverse=True,
    )

    return [
        chunk
        for score, _, chunk in ranked[:max_chunks]
        if score > 0
    ]


def number_presence(
    text: str,
    claim: str,
) -> dict:

    result = {}

    lower_text = text.lower()

    for number in numeric_terms(claim):

        cleaned = number.strip()

        result[cleaned] = (
            cleaned.lower() in lower_text
        )

    return result


# =========================================================
# CLAIM VERIFICATION
# =========================================================

def verify_claim(
    claim: str,
    source_url: str,
) -> dict:

    print(
        f"\nFetching source:\n"
        f"{source_url}",
        flush=True,
    )

    source_text = fetch_source_text(
        source_url
    )

    print(
        f"Extracted characters: "
        f"{len(source_text)}",
        flush=True,
    )

    # -----------------------------------------------------
    # Deterministic empty-source gate
    #
    # Source authority cannot compensate for the absence
    # of source content.
    #
    # If no meaningful text was extracted, the claim
    # cannot be verified and the LLM verifier must not
    # be called.
    # -----------------------------------------------------

    if not source_text.strip():

        return {
            "verification_status": "NOT_SUPPORTED",
            "supported_elements": [],
            "unsupported_elements": [
                claim
            ],
            "reason": (
                "Source fetched successfully but contained "
                "no extractable text. The claim cannot be "
                "verified from this source."
            ),
            "evidence_excerpt": "",
            "source_url": source_url,
            "extracted_characters": 0,
            "verification_method": (
                "DETERMINISTIC_EMPTY_SOURCE_GATE"
            ),
        }

    numbers = number_presence(
        source_text,
        claim,
    )

    relevant_chunks = rank_chunks(
        source_text,
        claim,
    )

    if not relevant_chunks:
        relevant_chunks = [
            source_text[:5000]
        ]

    evidence_text = "\n\n".join(
        (
            f"--- RELEVANT EXCERPT {index} ---\n"
            f"{chunk}"
        )
        for index, chunk in enumerate(
            relevant_chunks,
            start=1,
        )
    )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict source-verification agent. "
                    "You are given a candidate claim and text fetched "
                    "directly from the cited source. "
                    "The fetched source text is authoritative. "
                    "Do not use your memory or outside knowledge. "
                    "Do not repair missing evidence by inference. "
                    "Do not strengthen what the source says. "
                    "For quantitative claims, the claimed metrics must "
                    "be supported by the source text. "
                    "If an important number or causal relationship is "
                    "not supported, do not mark the full claim SUPPORTED. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
CANDIDATE CLAIM:

{claim}


SOURCE URL:

{source_url}


DETERMINISTIC NUMBER CHECK:

{json.dumps(numbers, indent=2)}


RELEVANT TEXT EXTRACTED DIRECTLY FROM THE SOURCE:

{evidence_text}


Classify the candidate claim as exactly one of:

SUPPORTED
= the important factual content and any material quantitative claims
  are directly supported by the supplied source text.

PARTIALLY_SUPPORTED
= some meaningful parts are directly supported, but one or more
  important details, metrics, causal claims, or interpretations are
  unsupported.

NOT_SUPPORTED
= the source text does not establish the core claim, materially
  contradicts it, or the claim depends on information absent from
  the supplied evidence.

Return exactly:

{{
  "verification_status": "SUPPORTED|PARTIALLY_SUPPORTED|NOT_SUPPORTED",
  "supported_elements": [
    ""
  ],
  "unsupported_elements": [
    ""
  ],
  "reason": "",
  "evidence_excerpt": ""
}}

The evidence_excerpt must be a short excerpt from the supplied source
text that best supports your decision. Do not invent quotations.
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=2000,
        timeout=120,
        extra_body={
            "thinking": {
                "type": "disabled"
            }
        },
    )

    result = json.loads(
        response.choices[0].message.content
        or "{}"
    )

    result["source_url"] = source_url
    result["number_presence"] = numbers

    return result


# =========================================================
# CLI
# =========================================================

def main():

    if len(sys.argv) != 3:

        print(
            "Usage:\n"
            "python verify_claim.py "
            "'<claim>' '<source_url>'"
        )

        sys.exit(1)

    claim = sys.argv[1]
    source_url = sys.argv[2]

    try:

        result = verify_claim(
            claim=claim,
            source_url=source_url,
        )

    except Exception as exc:

        print(
            f"\nERROR: {exc}"
        )

        sys.exit(1)

    print(
        "\n\nCLAIM VERIFICATION"
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
