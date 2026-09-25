import io
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


USER_AGENT = (
    "Mozilla/5.0 "
    "(X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/150.0.0.0 "
    "Safari/537.36"
)


def is_pdf_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def fetch_url(url: str) -> requests.Response:
    response = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(
        io.BytesIO(content)
    )

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = page.extract_text() or ""

        if not text.strip():
            continue

        pages.append(
            f"\n--- PAGE {page_number} ---\n{text}"
        )

    return "\n".join(pages)


def extract_html_text(content: bytes) -> str:
    soup = BeautifulSoup(
        content,
        "html.parser",
    )

    # Remove obvious non-content elements.
    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):
        element.decompose()

    text = soup.get_text(
        separator="\n"
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return "\n".join(lines)


def fetch_source_text(url: str) -> str:
    response = fetch_url(url)

    content_type = (
        response.headers
        .get("content-type", "")
        .lower()
    )

    if (
        is_pdf_url(url)
        or "application/pdf" in content_type
    ):
        return extract_pdf_text(
            response.content
        )

    return extract_html_text(
        response.content
    )


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python fetch_source.py <URL>"
        )
        sys.exit(1)

    url = sys.argv[1]

    print(
        f"\nFetching:\n{url}\n"
    )

    try:
        text = fetch_source_text(url)

    except Exception as exc:
        print(
            f"ERROR: {exc}"
        )
        sys.exit(1)

    print(
        f"Extracted characters: {len(text)}"
    )

    print(
        "\nFIRST 8000 CHARACTERS\n"
        "============================================================\n"
    )

    print(
        text[:8000]
    )


if __name__ == "__main__":
    main()
