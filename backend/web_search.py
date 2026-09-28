"""
Web search for the local-model steps, which cannot search on
their own the way Kimi's $web_search does.

SEARCH_PROVIDER in .env picks the backend:

- tavily (default when TAVILY_API_KEY is set): search API made
  for agents; free tier 1,000 searches/month (2026-09). Returns
  page text, so the caller can skip fetching pages.
- searxng: self-hosted (SEARXNG_URL), free, but the engines
  behind it block bursts of automated searches (CAPTCHAs).
"""

from __future__ import annotations

import os

import requests

import llm  # noqa: F401  (loads .env)


TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip()

SEARXNG_URL = os.environ.get("SEARXNG_URL", "").rstrip("/")

PROVIDER = (
    os.environ.get("SEARCH_PROVIDER", "").strip().lower()
    or ("tavily" if TAVILY_API_KEY else "searxng")
)

PAGE_CHARS = 3000


def search(
    query: str,
    limit: int = 8,
) -> list[dict]:
    """
    [{title, url, content, page?}] for a query. "page" is the
    page text when the provider returns it. Raises when the
    provider is unreachable or misconfigured.
    """

    if PROVIDER == "tavily":
        return search_tavily(query, limit)

    return search_searxng(query, limit)


def search_tavily(
    query: str,
    limit: int,
) -> list[dict]:

    if not TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY is not set in .env."
        )

    response = requests.post(
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {TAVILY_API_KEY}",
        },
        json={
            "query": query,
            # Basic = 1 credit per search.
            "search_depth": "basic",
            "max_results": limit,
            "include_raw_content": True,
        },
        timeout=60,
    )

    response.raise_for_status()

    return [
        {
            "title": str(item.get("title", "")).strip(),
            "url": str(item.get("url", "")).strip(),
            "content": str(item.get("content", "")).strip(),
            "page": str(item.get("raw_content") or "")[
                :PAGE_CHARS
            ],
        }
        for item in response.json().get("results", [])
        if item.get("url")
    ]


def search_searxng(
    query: str,
    limit: int,
) -> list[dict]:

    if not SEARXNG_URL:
        raise RuntimeError(
            "SEARXNG_URL is not set in .env."
        )

    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
            },
            timeout=30,
        )

    except requests.ConnectionError as exc:
        raise RuntimeError(
            f"SearXNG not reachable at {SEARXNG_URL}. "
            "Is the Perplexica/SearXNG container running?"
        ) from exc

    response.raise_for_status()

    return [
        {
            "title": str(item.get("title", "")).strip(),
            "url": str(item.get("url", "")).strip(),
            "content": str(item.get("content", "")).strip(),
        }
        for item in response.json().get("results", [])[:limit]
        if item.get("url")
    ]
