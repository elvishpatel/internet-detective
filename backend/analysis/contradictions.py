def find(evidence):
    support = [x for x in evidence if x["stance"] == "supporting"]
    oppose = [x for x in evidence if x["stance"] == "contradicting"]
    if support and oppose:
        return [{"severity": "high", "explanation": "Public sources contain both supportive and contradicting signals. The final score discounts the conflict rather than treating repetition as confirmation."}]
    return []
