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
                return (
                    candidate.parent / "基因组panel自动化系统"
                )  # Sibling layout (local dev)
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
    docs_enabled: bool = True
    business_timezone: str = "Asia/Shanghai"

    # --- Upload ---
    max_upload_size_mb: int = 100
    max_batch_upload_size_mb: int = 100
    max_batch_files: int = 50

    # --- Worker ---
    max_workers: int = 2
    recover_interrupted_tasks_on_startup: bool = True
    runtime_instance_lock_enabled: bool = True
    generation_process_isolation: bool = True
    generation_process_timeout_seconds: int = 600
    generation_process_termination_grace_seconds: float = 5.0

    # --- Patient enrichment ---
    # Optional external patient registry / operation-system lookup.
    # When set, the app will query this URL by sample_id after Excel upload.
    patient_enrichment_provider: str = "generic"
    patient_enrichment_url: str = ""
    patient_enrichment_token: str = ""
    patient_enrichment_timeout_seconds: float = 5.0
    patient_enrichment_hard_timeout_seconds: float = 12.0
    patient_enrichment_process_isolation: bool = True
    patient_enrichment_source_name: str = "patient_registry"
    patient_enrichment_aes_key: str = ""
    patient_enrichment_encrypt_flag: str = ""

    # --- Report download filename ---
    # Business naming format:
    # 患者姓名-癌种-项目名称-机构码-样本号-版本标签.docx
    report_filename_org_code: str = "mljy"
    report_filename_revision_label: str = "修改版"

    # --- Release scope ---
    # Comma-separated canonical project types unavailable in this production
    # release. The reportgen core has an independent matching guard so direct
    # CLI/worker paths cannot bypass the Web API restriction.
    disabled_project_types: str = ""

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

    @property
    def reference_report_dir(self) -> Path:
        return self.storage_root / "reference_reports"

    @property
    def feedback_dir(self) -> Path:
        return self.storage_root / "feedback"


settings = Settings()
