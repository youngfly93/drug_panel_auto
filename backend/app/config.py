"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


def _detect_project_root() -> Path:
    """
    Find the project root (the directory containing vercel.json or Makefile).
    Works for both local dev and Vercel deployment.
    """
    # Check env var first (set by api/index.py in Vercel)
    env_root = os.environ.get("RG_WEB_UPSTREAM_ROOT")
    if env_root:
        return Path(env_root)

    # Walk up from this file to find project root
    candidate = Path(__file__).resolve().parent  # app/
    for _ in range(5):
        candidate = candidate.parent
        if (candidate / "vercel.json").exists() or (candidate / "Makefile").exists():
            # Check if upstream files are in-repo (Vercel) or sibling (local dev)
            if (candidate / "config").exists() and (candidate / "reportgen").exists():
                return candidate  # In-repo layout (Vercel / self-contained)
            if (candidate.parent / "基因组panel自动化系统").exists():
                return candidate.parent / "基因组panel自动化系统"  # Sibling layout (local dev)
            return candidate

    # Fallback: assume sibling layout
    return Path(__file__).resolve().parents[3] / "基因组panel自动化系统"


def _detect_storage_root() -> Path:
    env_root = os.environ.get("RG_WEB_STORAGE_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[2] / "storage"


class Settings(BaseSettings):
    """App settings, overridable via environment variables or .env file."""

    # --- Paths ---
    upstream_root: Path = _detect_project_root()
    storage_root: Path = _detect_storage_root()

    # --- Database ---
    database_url: str = ""  # computed in model_post_init

    # --- Auth ---
    secret_key: str = "change-me-in-production"
    access_token_expire_hours: int = 8
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    # --- Upload ---
    max_upload_size_mb: int = 100

    # --- Worker ---
    max_workers: int = 2

    model_config = {"env_prefix": "RG_WEB_", "env_file": ".env", "extra": "ignore"}

    def model_post_init(self, __context) -> None:
        if not self.database_url:
            db_path = self.storage_root / "db" / "reportgen_web.sqlite"
            self.database_url = f"sqlite:///{db_path}"

    @property
    def upstream_config_dir(self) -> str:
        return str(self.upstream_root / "config")

    @property
    def upstream_template_dir(self) -> str:
        return str(self.upstream_root / "templates")

    @property
    def upload_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def report_dir(self) -> Path:
        return self.storage_root / "reports"

    @property
    def preview_dir(self) -> Path:
        return self.storage_root / "previews"

    @property
    def signature_dir(self) -> Path:
        return self.storage_root / "signatures"


settings = Settings()
