from __future__ import annotations

import time

from langchain_core.tools import Tool

from app.core.config import settings

try:
    from ddgs import DDGS as SEARCH_CLIENT
except ImportError:  # pragma: no cover - fallback for older installs
    from duckduckgo_search import DDGS as SEARCH_CLIENT


def duckduckgo_search(query: str) -> list[dict[str, str]]:
    """Search the web using DuckDuckGo and normalize the response."""
    if not query.strip():
        return []

    try:
        time.sleep(0.5)
        with SEARCH_CLIENT() as ddgs:
            results = list(
                ddgs.text(
                    query,
                    max_results=settings.max_search_results,
                    safesearch="moderate",
                )
            )
        return [
            {
                "title": item.get("title", ""),
                "snippet": item.get("body", ""),
                "url": item.get("href", ""),
            }
            for item in results
        ]
    except Exception as exc:
        return [{"title": "Search error", "snippet": str(exc), "url": ""}]


search_tool = Tool(
    name="web_search",
    description="Search the web for current information on a topic. Input: search query string.",
    func=duckduckgo_search,
)
