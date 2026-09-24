import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    override = os.environ.get("ASKFATTURE_DATA_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "AskFatture"
    return Path(__file__).resolve().parents[1] / "data"


class Settings(BaseSettings):
    app_name: str = "Ask Fatture"
    data_dir: Path = default_data_dir()
    ollama_url: str = "http://127.0.0.1:11434"
    # Piccolo e veloce; italiano decente. Alternative: qwen3:0.6b | qwen3:4b
    model: str = "qwen3:1.7b"
    host: str = "127.0.0.1"
    port: int = 8787
    model_config = SettingsConfigDict(env_prefix="ASKFATTURE_", env_file=".env", extra="ignore")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "ask-fatture.db"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(exist_ok=True)
