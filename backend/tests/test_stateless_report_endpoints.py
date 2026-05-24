import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.api import excel as excel_api  # noqa: E402
from app.api import report as report_api  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.dependencies import get_bridge  # noqa: E402
from app.config import settings  # noqa: E402


class FakeBridge:
    def read_excel(self, excel_path):
        return SimpleNamespace(path=excel_path)

    def get_sheet_names(self, _excel_data):
        return ["Meta", "Variations"]

    def get_sheet_info(self, _excel_data, sheet_name, excel_path=None):
        return {"rows": 1 if sheet_name == "Meta" else 2, "columns": 3}

    def detect_project_type(self, _excel_path, excel_data=None):
        return {
            "project_type": "crc_358_msi",
            "project_name": "结直肠癌358基因+MSI",
            "confidence": 0.99,
        }

    def validate_excel_data(self, _excel_data):
        return []

    def get_mapped_clinical_fields(self, _excel_data):
        return {"patient_name": "测试患者", "sample_id": "CASE001"}

    def generate_report(self, **kwargs):
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "fake_report.docx"
        output_file.write_bytes(b"PK\x03\x04fake-docx")
        return {
            "success": True,
            "output_file": str(output_file),
            "duration": 0.1,
            "errors": [],
            "warnings": [],
            "qa_status": "PASS",
            "qa_report": {"issues": [], "checks": {}},
        }


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(
        report_api.diff_svc,
        "run_auto_reference_diff",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        report_api.diff_svc,
        "report_diff_summary",
        lambda *_a, **_k: {},
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(excel_api.router, prefix="/api/v1")
    app.include_router(report_api.router, prefix="/api/v1")
    app.dependency_overrides[get_bridge] = lambda: FakeBridge()
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_inspect_excel_returns_sheet_and_field_payload(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/excel/inspect",
            files={"file": ("case.xlsx", b"placeholder", "application/vnd.ms-excel")},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["upload"]["detected_project_type"] == "crc_358_msi"
    assert data["sheets"][0] == {"name": "Meta", "rows": 1, "columns": 3}
    assert data["single_values"]["sample_id"] == "CASE001"


def test_generate_file_returns_inline_docx_payload(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/generate-file",
            files={"file": ("case.xlsx", b"placeholder", "application/vnd.ms-excel")},
            data={
                "clinical_info": '{"patient_name":"测试患者","sample_id":"CASE001"}',
                "project_type": "crc_358_msi",
                "project_name": "结直肠癌358基因+MSI",
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["success"] is True
    assert data["output_filename"] == "fake_report.docx"
    assert data["output_file_base64"].startswith("UEsD")
    assert data["qa_status"] == "PASS"
