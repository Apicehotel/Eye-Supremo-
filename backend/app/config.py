import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    """In exe Windows i dati restano in %LOCALAPPDATA%\\EyeSupremo."""
    override = os.environ.get("RANDFATTURE_DATA_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "EyeSupremo"
    return Path(__file__).resolve().parents[2] / "data"


def _env_files() -> tuple[str, ...]:
    candidates = [Path(".env"), default_data_dir() / ".env"]
    return tuple(str(path) for path in candidates if path.exists()) or (".env",)


class Settings(BaseSettings):
    app_name: str = "Eye Supremo"
    data_dir: Path = default_data_dir()
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
    # Credenziali catalogo centrale MultiHotel (PIN ≠ PIN locale Eye)
    supabase_central_username: str = "sviluppatore"
    supabase_central_pin: str | None = None
    # Edge Function gateway (preferito). Se vuoto → RPC rest/v1/rpc/eye_central_invoice_page
    supabase_central_gateway: str | None = (
        "https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway"
    )
    # Azione richiesta dal gateway (es. invoice_page). Vuoto = prova elenco azioni note.
    supabase_central_gateway_action: str = "invoice_page"
    model_config = SettingsConfigDict(
        env_prefix="RANDFATTURE_",
        env_file=_env_files(),
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
        if not self.supabase_central_pin:
            return False
        if self.supabase_central_gateway:
            return True
        return bool(self.supabase_url and self.supabase_rest_key)

    @property
    def reviews_configured(self) -> bool:
        """Recensioni centrali: RPC eye_central_review_page (serve URL+chiave+PIN)."""
        return bool(
            self.supabase_central_pin
            and self.supabase_url
            and self.supabase_rest_key
        )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(exist_ok=True)
(settings.data_dir / "backups").mkdir(exist_ok=True)
(settings.data_dir / "supabase_mirror").mkdir(exist_ok=True)
