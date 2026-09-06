"""Mandatory hosted AI verification via Hugging Face's OpenAI-compatible router."""
import httpx
from backend.config import settings


class AIUnavailableError(RuntimeError):
    """Raised when a required verifier cannot safely review a completed case."""


class HuggingFaceProvider:
    name = "Hugging Face Inference Providers"
    endpoint = "https://router.huggingface.co/v1/chat/completions"

    async def review_conclusion(self, claim, evidence, score):
        if not settings.huggingface_api_key:
            raise AIUnavailableError("AI verification is required, but HUGGINGFACE_API_KEY is not configured.")
        ledger = "\n\n".join(
            f"EVIDENCE {i + 1}\nSTANCE: {item['stance']}\nSOURCE: {item['source_title']} ({item['source_url']})\nEXCERPT: {item['excerpt']}"
            for i, item in enumerate(evidence[:10])
        ) or "No qualifying excerpts were extracted."
        prompt = f"""You are the required verification pass for an evidence investigation.
Use only the supplied evidence ledger. Never invent facts, sources, URLs, dates, or quotes.

CLAIM: {claim}
DETERMINISTIC SCORE: {score['confidence']}/100 ({score['label']})

{ledger}

Respond in 2–5 concise sentences: say whether the verdict overstates the supplied evidence, identify the strongest support and strongest limitation, and state whether any excerpt was misclassified. Do not give a new numeric score."""
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}", "Content-Type": "application/json"}
        payload = {"model": settings.huggingface_model, "messages": [{"role": "system", "content": "You are a careful evidence reviewer."}, {"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 300, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                if response.status_code >= 400:
                    detail = response.text[:500]
                    raise AIUnavailableError(
                        f"Required Hugging Face verification failed: {response.status_code} for model "
                        f"'{settings.huggingface_model}'. Provider said: {detail}"
                    )
            data = response.json()
            note = data["choices"][0]["message"]["content"].strip()
            if not note: raise AIUnavailableError("The AI verifier returned an empty review.")
            return {"available": True, "required": True, "provider": self.name, "model": settings.huggingface_model, "note": note[:1600]}
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise AIUnavailableError(f"Required Hugging Face verification failed: {exc}") from exc
