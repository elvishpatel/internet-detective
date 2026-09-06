from bs4 import BeautifulSoup
try:
    import trafilatura
except ImportError:  # Allows the API to retain a safe BeautifulSoup fallback during minimal installs.
    trafilatura = None


def extract_html(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else url)
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False) if trafilatura else None
    text = extracted or soup.get_text(" ", strip=True)
    return {"title": title[:300], "text": " ".join(text.split())[:120000]}
