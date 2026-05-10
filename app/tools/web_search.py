import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def web_search(query: str, num_results: int = 5) -> str:
    """Search DuckDuckGo and return top results as formatted text."""
    try:
        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "wt-wt"},
            headers=_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Search failed: {exc}"

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for r in soup.select(".result.results_links")[: int(num_results)]:
        title_el = r.select_one(".result__a")
        snippet_el = r.select_one(".result__snippet")
        url_el = r.select_one(".result__url")
        title = title_el.get_text(strip=True) if title_el else "No title"
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        url = url_el.get_text(strip=True) if url_el else ""
        results.append(f"**{title}**\n{url}\n{snippet}")

    if not results:
        return f"No results found for: {query!r}"
    return "\n\n".join(results)
