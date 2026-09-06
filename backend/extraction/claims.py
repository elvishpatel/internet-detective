import re

STOP = {"is", "are", "was", "were", "the", "a", "an", "to", "in", "of", "for", "and", "or", "about", "this", "that"}


def decompose(claim: str) -> dict:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", claim)
    meaningful = [w for w in words if w.lower() not in STOP]
    subject = " ".join(meaningful[:3]) or claim
    lower = claim.lower()
    action = next((x for x in ["launch", "expand", "acquire", "build", "prepare", "release", "hire", "invest"] if x in lower), "investigate")
    location = next((x for x in ["india", "china", "europe", "usa", "uk", "canada", "japan"] if x in lower), "unspecified")
    kind = "product launch" if any(x in lower for x in ["launch", "product", "release"]) else "public claim"
    return {"subject": subject, "action": action, "object": " ".join(meaningful[3:9]) or "unspecified", "location": location.title(), "claim_type": kind}


def build_queries(claim: str, parts: dict, maximum: int) -> list[str]:
    subject = parts["subject"]
    action = parts["action"]
    variants = [claim, f"{subject} {action}", f"{subject} official announcement", f"{subject} executive statement", f"{subject} news", f"{subject} hiring jobs", f"{subject} regulatory filing", f"{subject} supplier", f"{subject} patent", f"site:github.com {subject}", f"site:{_domain_hint(subject)} {action}"]
    if parts["location"] != "Unspecified": variants.extend([f"{subject} {parts['location']}", f"{subject} {parts['location']} {action}"])
    seen = []
    for query in variants:
        if query not in seen: seen.append(query)
    return seen[:maximum]


def _domain_hint(subject): return re.sub(r"[^a-z0-9]", "", subject.lower().split()[0]) + ".com"
