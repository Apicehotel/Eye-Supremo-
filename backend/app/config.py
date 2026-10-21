import os
import sys
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "EyeSupremo"
    return Path(__file__).resolve().parents[2] / "data"


class Settings(BaseSettings):
    app_name: str = "Eye Supremo"
    data_dir: Path = default_data_dir()
    max_upload_mb: int = 100
    ollama_url: str = "http://127.0.0.1:11434"
    # Layer mirror: fast = PC ufficio; chat_model = qualità (escalation)
    chat_model_fast: str = "llama3.2:3b"
    chat_model: str = "qwen3:8b"
    chat_model_alternative: str = "mistral:7b"
    embedding_model: str = "qwen3-embedding:0.6b"
    ai_layer_policy: str = "fast_first"
    supabase_url: str | None = "https://ooqlfldcrnkudhgjnied.supabase.co"
    supabase_publishable_key: str | None = "sb_publishable_Oiu7IOhuUd6YPEDmmSa7zA_ngNuiSlX"
    supabase_access_token: str | None = None
    # Logical namespace inside the temporary shared Supabase project.
    # Existing RPC compatibility remains in public until the staged cutover.
    supabase_schema: str = "eye_supremo"
    # Credenziali centrali: le vecchie variabili EYESUPREMO_CENTRAL_USERNAME / _PIN lasciate su un PC non
    # hanno più effetto (causavano «Credenziali non valide»). Per cambiarle servono i nomi *_OVERRIDE.
    central_username: str = Field("supremo", validation_alias="EYESUPREMO_CENTRAL_USERNAME_OVERRIDE")
    central_pin: str = Field("000000", validation_alias="EYESUPREMO_CENTRAL_PIN_OVERRIDE")
    central_function: str = "eye-central-gateway"
    central_identity_enabled: bool = True
    central_identity_function: str = "eye-identity"
    offline_access_days: int = Field(7, ge=1, le=30)
    sync_enabled: bool = False
    # Al primo avvio/installazione scarica fatture+recensioni in cache SQLite.
    cache_bootstrap_on_start: bool = True
    live_search_debounce_ms: int = 180
    api_version: str = "v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8765"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]
    model_config = SettingsConfigDict(env_prefix="EYESUPREMO_", env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'eye-supremo.db').as_posix()}"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(exist_ok=True)
(settings.data_dir / "backups").mkdir(exist_ok=True)
(settings.data_dir / "reviews").mkdir(exist_ok=True)

