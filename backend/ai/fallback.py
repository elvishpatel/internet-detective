class FallbackProvider:
    name = "Deterministic evidence review"
    async def review_conclusion(self, claim, evidence, score):
        return {"available": False, "provider": self.name, "note": "AI verification was not used. The verdict is based on the transparent evidence engine."}
