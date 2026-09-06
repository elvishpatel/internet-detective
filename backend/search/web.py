from urllib.parse import quote_plus, urlparse
import httpx
from bs4 import BeautifulSoup
from backend.search.base import Source
from backend.utils.urls import is_safe_public_url, normalize_url

HEADERS = {"User-Agent": "InternetDetective/1.0 (+public research; respectful rate limits)"}


async def discover(query: str, limit: int = 8) -> list[Source]:
    # DuckDuckGo's lightweight HTML endpoint is used as a no-key discovery option.
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=12) as client:
            response = await client.get("https://html.duckduckgo.com/html/?q=" + quote_plus(query))
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        output = []
        for link in soup.select("a.result__a"):
            url = normalize_url(link.get("href", ""))
            if not is_safe_public_url(url): continue
            result = link.find_parent(class_="result")
            snippet = result.select_one(".result__snippet").get_text(" ", strip=True) if result and result.select_one(".result__snippet") else ""
            output.append(Source(url, link.get_text(" ", strip=True), snippet, urlparse(url).netloc.lower()))
            if len(output) >= limit: break
        return output
    except Exception:
        return []
