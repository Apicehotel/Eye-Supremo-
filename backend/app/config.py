from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (…/Eye-Supremo-): config vive in backend/app/
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "RandFatture"
    data_dir: Path = _REPO_ROOT / "data"
    max_upload_mb: int = 30
    # Profilo light per PC ~16 GB RAM
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:4b"
    embedding_model: str = "nomic-embed-text"
    # Supabase MultiHotel = Storage blob + catalogo metadati eye_central_*
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_anon_key: str | None = None
    supabase_bucket: str = "eye-invoices"
    # Radice path content-addressable: invoices/{kind}/{hh}/{hash}{ext}
    supabase_storage_root: str = "invoices"
    # Credenziali RPC eye_central_invoice_page (PIN MultiHotel, non PIN locale Eye)
    supabase_central_username: str = "sviluppatore"
    supabase_central_pin: str | None = None
    model_config = SettingsConfigDict(
        env_prefix="RANDFATTURE_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'randfatture.db').as_posix()}"

    @property
    def supabase_rest_key(self) -> str | None:
        return self.supabase_service_key or self.supabase_anon_key

    @property
    def storage_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def central_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_rest_key and self.supabase_central_pin)


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(exist_ok=True)
(settings.data_dir / "backups").mkdir(exist_ok=True)
(settings.data_dir / "supabase_mirror").mkdir(exist_ok=True)
