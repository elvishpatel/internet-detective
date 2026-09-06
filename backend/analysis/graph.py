import re

def build(claim: str, evidence: list[dict]) -> dict:
    nodes = [{"id": "claim", "label": "Claim", "type": "claim"}]
    links = []
    domains = []
    for item in evidence:
        domain = item["domain"]
        if domain not in domains:
            domains.append(domain); nodes.append({"id": domain, "label": domain.replace("www.", "")[:24], "type": "source"})
            links.append({"source": domain, "target": "claim", "type": item["stance"]})
    entities = []
    for word in re.findall(r"\b[A-Z][A-Za-z0-9]+\b", claim):
        if word not in entities and word not in {"Is", "Did", "The", "A"}: entities.append(word)
    for entity in entities[:5]:
        nodes.append({"id": entity, "label": entity, "type": "entity"}); links.append({"source": entity, "target": "claim", "type": "entity"})
    return {"nodes": nodes, "links": links}
