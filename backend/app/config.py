import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "EyeSupremo"
    return Path(__file__).resolve().parents[2] / "data"


class Settings(BaseSettings):
    app_name: str = "Eye Supremo"
    data_dir: Path = default_data_dir()
    max_upload_mb: int = 30
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:8b"
    embedding_model: str = "qwen3-embedding:0.6b"
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_access_token: str | None = None
    sync_enabled: bool = False
    live_search_debounce_ms: int = 180
    model_config = SettingsConfigDict(env_prefix="EYESUPREMO_", env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'eye-supremo.db').as_posix()}"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(exist_ok=True)
(settings.data_dir / "backups").mkdir(exist_ok=True)
(settings.data_dir / "reviews").mkdir(exist_ok=True)
