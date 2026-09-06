def score(evidence: list[dict], source_count: int) -> dict:
    support = [x for x in evidence if x["stance"] == "supporting"]
    contradict = [x for x in evidence if x["stance"] == "contradicting"]
    support_raw = sum(x["strength"] * x["authority"] for x in support)
    contradiction_raw = sum(x["strength"] * x["authority"] for x in contradict)
    independent = len({x["domain"] for x in support})
    positive = min(56, round(support_raw * 22)) + min(18, independent * 4)
    negative = min(35, round(contradiction_raw * 25))
    confidence = max(0, min(100, 18 + positive - negative)) if support else max(8, 25 - negative)
    label = "Likely" if confidence >= 61 else "Uncertain" if confidence >= 41 else "Insufficient public evidence"
    return {"confidence": confidence, "label": label, "components": [{"label": "Relevant supporting evidence", "value": min(56, round(support_raw * 22))}, {"label": "Independent reporting domains", "value": min(18, independent * 4)}, {"label": "Contradicting evidence", "value": -negative}, {"label": "Direct confirmation not found", "value": -12 if confidence < 70 else 0}], "independent_chains": independent, "source_count": source_count}
