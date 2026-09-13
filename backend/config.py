from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "./data/investigator.db")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5500")
    max_queries: int = int(os.getenv("MAX_QUERIES", "30"))
    max_urls: int = int(os.getenv("MAX_URLS", "120"))
    max_documents: int = int(os.getenv("MAX_DOCUMENTS", "30"))
    max_entities: int = int(os.getenv("MAX_ENTITIES", "40"))
    enable_local_ai: bool = os.getenv("ENABLE_LOCAL_AI", "false").lower() == "true"
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    require_ai_verification: bool = os.getenv("REQUIRE_AI_VERIFICATION", "true").lower() == "true"
    # When true, a total verifier outage completes the case with a prominent
    # "not reviewed" banner instead of throwing the whole investigation away.
    # The deterministic engine was always the source of truth; losing the review
    # should degrade the product, not delete it.
    ai_degrade_gracefully: bool = os.getenv("AI_DEGRADE_GRACEFULLY", "true").lower() == "true"
    ai_provider: str = os.getenv("AI_PROVIDER", "huggingface").lower()

    huggingface_api_key: str = os.getenv("HUGGINGFACE_API_KEY", "")
    # Leave HUGGINGFACE_MODEL empty to let the router catalogue decide. Pin a repo
    # id ("Qwen/Qwen2.5-7B-Instruct") or an exact pair ("Qwen/Qwen2.5-7B-Instruct:together")
    # only if you have a reason to; it is tried first, then the fallbacks below.
    huggingface_model: str = os.getenv("HUGGINGFACE_MODEL", "")
    # Comma-separated extra candidates tried before the built-in defaults.
    huggingface_model_fallbacks: str = os.getenv("HUGGINGFACE_MODEL_FALLBACKS", "")
    # "auto" lets Hugging Face pick the downstream provider. Pin a slug such as
    # "together", "novita", "nebius", or "fireworks-ai" only to override it.
    huggingface_provider: str = os.getenv("HUGGINGFACE_PROVIDER", "auto")
    # Ask the router which models are actually live before spending requests.
    huggingface_discover_models: bool = os.getenv("HUGGINGFACE_DISCOVER_MODELS", "true").lower() == "true"
    huggingface_catalog_ttl: int = int(os.getenv("HUGGINGFACE_CATALOG_TTL", "900"))
    huggingface_max_attempts: int = int(os.getenv("HUGGINGFACE_MAX_ATTEMPTS", "8"))
    huggingface_timeout: float = float(os.getenv("HUGGINGFACE_TIMEOUT", "35"))


settings = Settings()
