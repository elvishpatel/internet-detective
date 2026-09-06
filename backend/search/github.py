from urllib.parse import quote_plus
import httpx
from backend.search.base import Source

async def discover(query: str, limit: int = 5) -> list[Source]:
    try:
        async with httpx.AsyncClient(headers={"Accept": "application/vnd.github+json", "User-Agent": "InternetDetective"}, timeout=12) as client:
            result = (await client.get(f"https://api.github.com/search/repositories?q={quote_plus(query)}&per_page={limit}")).json()
        return [Source(x["html_url"], x["full_name"], x.get("description") or "", "github.com", "github", x.get("updated_at"), "github") for x in result.get("items", [])]
    except Exception: return []
