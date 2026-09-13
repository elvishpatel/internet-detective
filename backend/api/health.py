from fastapi import APIRouter
import httpx

from backend.ai import huggingface as hf
from backend.config import settings

router = APIRouter()


@router.get("/api/health")
def health():
    """Cheap liveness check plus a secret-free view of the AI configuration."""
    return {
        "status": "ok",
        "service": "internet-detective",
        "ai": {
            "provider": settings.ai_provider,
            "required": settings.require_ai_verification,
            "degrade_gracefully": settings.ai_degrade_gracefully,
            "key_configured": bool(settings.huggingface_api_key),
            "model": settings.huggingface_model or "auto",
            "downstream_provider": settings.huggingface_provider or "auto",
            "discovery": settings.huggingface_discover_models,
        },
    }


@router.get("/api/health/ai")
async def health_ai():
    """Live probe: does the verifier actually answer right now, and with which model?

    Deliberately separate from /api/health so uptime pings stay free. Returns 200
    with ok=false rather than an error status, so a browser shows the diagnosis.
    """
    if settings.ai_provider != "huggingface":
        return {"ok": None, "detail": f"AI_PROVIDER is '{settings.ai_provider}'; this probe only covers Hugging Face."}
    if not settings.huggingface_api_key:
        return {"ok": False, "detail": "HUGGINGFACE_API_KEY is not set on this service."}

    headers = {"Authorization": f"Bearer {settings.huggingface_api_key}", "Content-Type": "application/json"}
    messages = [{"role": "user", "content": "Reply with the single word: ready"}]
    tried: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=settings.huggingface_timeout) as client:
            live = await hf.catalog(client, headers)
            attempts = hf.plan_attempts(live)
            for model_id in attempts:
                try:
                    await hf.chat_once(client, headers, model_id, messages)
                except hf.AIConfigurationError as fatal:
                    return {"ok": False, "fatal": True, "tried": tried, "detail": str(fatal)}
                except Exception as exc:
                    tried.append(f"{model_id}: {exc}")
                    continue
                return {"ok": True, "model": model_id, "catalogue_size": len(live), "skipped": tried}
    except Exception as exc:  # network-level failure reaching the router at all
        return {"ok": False, "tried": tried, "detail": f"Could not reach the router: {exc}"}

    return {
        "ok": False,
        "tried": tried,
        "detail": "No candidate model answered. Check the token's Inference Providers permission and your remaining credits.",
    }
