import re
from urllib.parse import urlparse

SUPPORT = ("launch", "announc", "confirm", "expand", "opening", "hiring", "job", "investment", "partnership", "release", "filed", "approved")
CONTRADICT = ("deny", "denied", "not planned", "no plans", "cancel", "cancelled", "false", "rumor", "rumour")

def authority(url: str) -> float:
    domain = urlparse(url).netloc.lower()
    if domain.endswith(".gov") or domain.endswith(".edu"): return .95
    if "github.com" in domain: return .55
    if any(x in domain for x in ["reuters.com", "apnews.com", "bbc."]): return .80
    if any(x in domain for x in ["linkedin.com", "greenhouse.io", "lever.co"]): return .65
    return .48

def evidence_from_document(claim: str, source: dict, text: str) -> list[dict]:
    terms = [x.lower() for x in re.findall(r"[A-Za-z]{4,}", claim)][:8]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    found = []
    for sentence in sentences:
        lower = sentence.lower()
        relevance = sum(t in lower for t in terms) / max(1, len(terms))
        if relevance < .12: continue
        stance = "contradicting" if any(x in lower for x in CONTRADICT) else ("supporting" if any(x in lower for x in SUPPORT) else "context")
        strength = round(min(.92, authority(source["url"]) * (.55 + relevance * .45) * (1.12 if stance != "context" else .75)), 2)
        found.append({"source_url": source["url"], "source_title": source["title"], "domain": source["domain"], "stance": stance, "strength": strength, "authority": round(authority(source["url"]), 2), "excerpt": sentence[:500], "reasoning": "Matches claim entities and contains a relevant public signal." if stance != "context" else "Provides related context but does not directly establish the claim."})
        if len(found) == 2: break
    return found
