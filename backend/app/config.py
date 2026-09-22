from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RandFatture"
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    max_upload_mb: int = 30
    # Profilo light per PC ~16 GB RAM
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:4b"
    embedding_model: str = "nomic-embed-text"
    # Supabase = solo Storage file (non database fatture)
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_bucket: str = "invoices"
    model_config = SettingsConfigDict(env_prefix="RANDFATTURE_", env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'randfatture.db').as_posix()}"

    @property
    def storage_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(exist_ok=True)
(settings.data_dir / "backups").mkdir(exist_ok=True)
(settings.data_dir / "supabase_mirror").mkdir(exist_ok=True)
