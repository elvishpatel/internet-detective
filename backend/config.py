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
    ai_provider: str = os.getenv("AI_PROVIDER", "huggingface").lower()
    huggingface_api_key: str = os.getenv("HUGGINGFACE_API_KEY", "")
    huggingface_model: str = os.getenv("HUGGINGFACE_MODEL", "Qwen/Qwen2.5-7B-Instruct")


settings = Settings()
