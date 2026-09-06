import httpx
from backend.config import settings

class OllamaProvider:
    name = "Ollama"
    async def review_conclusion(self, claim, evidence, score):
        prompt = "Review only the supplied evidence. Do not invent facts or sources. In 2 sentences, flag unsupported inference.\nClaim: " + claim + "\nEvidence:\n" + "\n".join(x["excerpt"] for x in evidence[:8])
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.ollama_url.rstrip("/") + "/api/generate", json={"model": "llama3.2:3b", "prompt": prompt, "stream": False})
            response.raise_for_status()
            note = response.json().get("response", "")[:1600]
            if not note: raise RuntimeError("Ollama returned an empty AI review.")
            return {"available": True, "required": True, "provider": self.name, "model": "llama3.2:3b", "note": note}
