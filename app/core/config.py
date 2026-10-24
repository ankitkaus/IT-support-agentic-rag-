from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # App
    app_name: str = "Enterprise IT Support Agentic RAG Copilot"
    app_env: str = "development"

    # API keys (.env se aayengi)
    groq_api_key: str = ""
    tavily_api_key: str = ""
    pinecone_api_key: str = ""
    google_api_key: str = ""

    # Pinecone
    pinecone_index_name: str = "fde-it-support-rag"
    pinecone_namespace: str = "company-it-kb"

    # LLM (Groq)
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings (Gemini)
    embedding_model: str = "models/gemini-embedding-001"
    embedding_dimension: int = 3072# Pinecone index ki dimension ke same honi chahiye

    # RAG
    top_k: int = 4
    max_retries: int = 1

    # Admin / storage
    admin_api_key: str = "change-me"
    audit_db_path: str = str(BASE_DIR / "data" / "audit.db")
    upload_dir: str = str(BASE_DIR / "uploads")
    sample_kb_dir: str = str(BASE_DIR / "data" / "sample_kb")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()