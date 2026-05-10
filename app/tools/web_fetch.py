import html2text
import httpx

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0
_h2t.single_line_break = True


def web_fetch(url: str, max_chars: int = 4000) -> str:
    """Fetch a webpage and return its plain-text content."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "text/html" in ct or "application/xhtml" in ct:
            text = _h2t.handle(resp.text)
        else:
            text = resp.text
        # collapse blank lines
        text = "\n".join(line for line in text.splitlines() if line.strip())
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[...truncated at {max_chars} chars]"
        return text.strip()
    except Exception as exc:
        return f"Fetch failed: {exc}"
