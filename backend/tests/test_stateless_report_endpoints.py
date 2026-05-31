import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.api import batch as batch_api  # noqa: E402
from app.api import excel as excel_api  # noqa: E402
from app.api import report as report_api  # noqa: E402
from app.api import task as task_api  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.dependencies import get_bridge  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import clinical_info_service as clinical_svc  # noqa: E402
from app.services.reportgen_bridge import ReportGenBridge  # noqa: E402


class FakeBridge:
    def __init__(self):
        self.detect_result = {
            "project_type": "crc_358_msi",
            "project_name": "结直肠癌358基因+MSI",
            "confidence": 0.99,
            "detected": True,
        }
        self.last_generate_kwargs = None

    def read_excel(self, excel_path):
        return SimpleNamespace(path=excel_path)

    def get_sheet_names(self, _excel_data):
        return ["Meta", "Variations"]

    def get_sheet_info(self, _excel_data, sheet_name, excel_path=None):
        return {"rows": 1 if sheet_name == "Meta" else 2, "columns": 3}

    def detect_project_type(self, _excel_path, excel_data=None):
        return dict(self.detect_result)

    def infer_project_type_from_text(self, text):
        if "358" in str(text):
            return {
                "project_type": "crc_358_msi",
                "project_name": "结直肠癌358基因+MSI",
                "confidence": 1.0,
                "detected": True,
            }
        return {
            "project_type": None,
            "project_name": None,
            "confidence": 0.0,
            "detected": False,
        }

    def validate_excel_data(self, _excel_data):
        return []

    def build_preview_summary(self, **_kwargs):
        return {
            "schema_version": "1.0",
            "preview": True,
            "project_type": "crc_358_msi",
            "patient": {"sample_id": "CASE001"},
            "biomarkers": {
                "tmb": {"status": "L", "summary": "6.5 mutations/Mb，TMB-L"},
                "msi": {"status": "MSS", "summary": "微卫星稳定型，MSS"},
            },
            "variants": {
                "total": 1,
                "drug_related": 1,
                "key_rows": [{"gene": "KRAS", "variant_site": "p.G12S"}],
            },
            "drugs": {
                "targeted_count": 1,
                "targeted_rows": [{"gene": "KRAS", "caution_drugs": "西妥昔单抗"}],
            },
        }

    def get_mapped_clinical_fields(self, _excel_data):
        return {"patient_name": "测试患者", "sample_id": "CASE001"}

    def generate_report(self, **kwargs):
        self.last_generate_kwargs = kwargs
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{Path(kwargs.get('excel_path') or 'fake_report').stem}.docx"
        output_file.write_bytes(b"PK\x03\x04fake-docx")
        summary_file = output_file.with_suffix(".summary.json")
        summary_file.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "generation_id": output_file.stem,
                    "patient": {"sample_id": "CASE001"},
                    "variants": {"total": 1, "drug_related": 1},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {
            "success": True,
            "output_file": str(output_file),
            "duration": 0.1,
            "errors": [],
            "warnings": [],
            "qa_status": "PASS",
            "qa_report": {"issues": [], "checks": {}},
            "report_summary_file": str(summary_file),
        }


class FailOnceBridge(FakeBridge):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    def generate_report(self, **kwargs):
        excel_stem = Path(kwargs.get("excel_path") or "").stem
        if excel_stem == "case2" and not self.failed_once:
            self.failed_once = True
            return {
                "success": False,
                "output_file": None,
                "duration": 0.1,
                "errors": ["synthetic failure"],
                "warnings": [],
                "qa_status": None,
                "qa_report": {"issues": [], "checks": {}},
                "report_summary_file": None,
            }
        return super().generate_report(**kwargs)


class SlowBridge(FakeBridge):
    def generate_report(self, **kwargs):
        time.sleep(0.2)
        return super().generate_report(**kwargs)


def _client(tmp_path, monkeypatch, bridge=None):
    bridge = bridge or FakeBridge()
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
    monkeypatch.setattr(
        batch_api.diff_svc,
        "run_batch_reference_diff",
        lambda *_a, **_k: {"status": "PASS", "summary": {}},
    )

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(report_api, "SessionLocal", SessionLocal)
    monkeypatch.setattr(batch_api, "SessionLocal", SessionLocal)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(excel_api.router, prefix="/api/v1")
    app.include_router(report_api.router, prefix="/api/v1")
    app.include_router(batch_api.router, prefix="/api/v1")
    app.include_router(task_api.router, prefix="/api/v1")
    app.dependency_overrides[get_bridge] = lambda: bridge
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
    assert data["preview_summary"]["preview"] is True
    assert data["preview_summary"]["variants"]["total"] == 1


def test_patient_enrichment_marvelbio_posts_encrypted_sample(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "result": {
                        "status": 200,
                        "message": "成功",
                        "data": {
                            "userName": "运营患者",
                            "sex": "男",
                            "age": 70,
                            "cancerName": "乙状结肠癌",
                            "sampleType": "新鲜组织",
                            "sampleTime": "2025-11-21",
                            "sampleReachTime": "2025-11-22",
                            "hospital": "运营医院",
                            "department": "结直肠肿瘤科",
                        },
                    }
                },
                ensure_ascii=False,
            ).encode("utf-8")

    requests = []

    def fake_urlopen(req, timeout):
        requests.append(req)
        assert timeout == 5.0
        assert req.full_url == "https://webapi.example.test/ngsapi/getNgsSample"
        assert req.headers["Content-type"] == "application/json"
        body = json.loads(req.data.decode("utf-8"))
        assert body["encryptFlag"] == "fixed-flag"
        assert body["encryptCode"]
        assert body["encryptCode"] != "CASE001"
        return FakeResponse()

    monkeypatch.setattr(clinical_svc, "_load_patient_info", lambda: {"patients": {}})
    monkeypatch.setattr(clinical_svc.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(settings, "patient_enrichment_provider", "marvelbio")
    monkeypatch.setattr(
        settings,
        "patient_enrichment_url",
        "https://webapi.example.test/ngsapi/getNgsSample",
    )
    monkeypatch.setattr(settings, "patient_enrichment_aes_key", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(settings, "patient_enrichment_encrypt_flag", "fixed-flag")
    monkeypatch.setattr(settings, "patient_enrichment_timeout_seconds", 5.0)

    result = clinical_svc.enrich_patient("CASE001", project_type="crc_358_msi")

    assert len(requests) == 1
    assert result.found is True
    assert result.source == "marvelbio"
    assert result.fields["patient_name"] == "运营患者"
    assert result.fields["gender"] == "男"
    assert result.fields["age"] == 70
    assert result.fields["cancer_type"] == "乙状结肠癌"
    assert result.fields["clinical_diagnosis"] == "乙状结肠癌"
    assert result.fields["sample_type"] == "新鲜组织"
    assert result.fields["collection_date"] == "2025-11-21"
    assert result.fields["receive_date"] == "2025-11-22"
    assert result.fields["hospital"] == "运营医院"
    assert result.fields["department"] == "结直肠肿瘤科"

    merged = clinical_svc.merge_enrichment_into_values(
        {
            "hospital": "某某医院",
            "department": "肿瘤科",
            "sample_type": "组织",
            "patient_name": "已手动填写",
        },
        result,
    )
    assert merged["hospital"] == "运营医院"
    assert merged["department"] == "结直肠肿瘤科"
    assert merged["sample_type"] == "新鲜组织"
    assert merged["patient_name"] == "已手动填写"


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
    assert data["output_filename"] == "测试患者-癌种未填-结直肠癌358基因+msi-mljy-case001-修改版.docx"
    assert data["output_file_base64"].startswith("UEsD")
    assert data["qa_status"] == "PASS"


def test_generate_file_infers_project_type_from_form_project_name(
    tmp_path, monkeypatch
):
    bridge = FakeBridge()
    bridge.detect_result = {
        "project_type": None,
        "project_name": None,
        "confidence": 0.0,
        "detected": False,
    }

    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        response = client.post(
            "/api/v1/reports/generate-file",
            files={
                "file": (
                    "上传使用Excel表：lz258792.xlsx",
                    b"placeholder",
                    "application/vnd.ms-excel",
                )
            },
            data={
                "clinical_info": '{"patient_name":"测试患者","sample_id":"CASE001","project_name":"结直肠癌358基因+MSI"}',
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["success"] is True
    assert bridge.last_generate_kwargs["project_type"] == "crc_358_msi"
    assert bridge.last_generate_kwargs["project_name"] == "结直肠癌358基因+MSI"


def test_generate_file_async_returns_task_and_completes(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/generate-file-async",
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
        assert data["output_file"] is None

        status_response = None
        for _ in range(20):
            status_response = client.get(f"/api/v1/reports/{data['task_id']}")
            if status_response.json()["data"]["status"] != "running":
                break
            time.sleep(0.05)

    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["status"] == "completed"
    assert status["output_path"].endswith("case.docx")
    assert status["report_summary_file"].endswith("case.summary.json")


def test_batch_files_returns_progress_rows_and_zip(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                (
                    "files",
                    ("case1.xlsx", b"placeholder1", "application/vnd.ms-excel"),
                ),
                (
                    "files",
                    ("case2.xlsx", b"placeholder2", "application/vnd.ms-excel"),
                ),
            ],
            data={
                "project_type": "crc_358_msi",
                "project_name": "结直肠癌358基因+MSI",
            },
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]

        status_response = None
        for _ in range(20):
            status_response = client.get(f"/api/v1/reports/{task_id}")
            if status_response.json()["data"]["status"] != "running":
                break
            time.sleep(0.05)

        results_response = client.get(f"/api/v1/reports/{task_id}/batch-results")
        zip_response = client.get(f"/api/v1/reports/{task_id}/batch/download")

    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["task_type"] == "batch"
    assert status["status"] == "completed"
    assert status["completed_files"] == 2
    assert status["failed_files"] == 0
    assert results_response.status_code == 200
    rows = results_response.json()["data"]["items"]
    assert [row["status"] for row in rows] == ["completed", "completed"]
    assert rows[0]["download_url"].endswith("/batch-results/1/download")
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"].startswith("application/zip")


def test_batch_failed_rows_can_be_retried(tmp_path, monkeypatch):
    bridge = FailOnceBridge()
    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"placeholder1", "application/vnd.ms-excel")),
                ("files", ("case2.xlsx", b"placeholder2", "application/vnd.ms-excel")),
            ],
            data={"project_type": "crc_358_msi"},
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]

        first_status_response = None
        for _ in range(30):
            first_status_response = client.get(f"/api/v1/reports/{task_id}")
            if first_status_response.json()["data"]["status"] != "running":
                break
            time.sleep(0.05)

        first_status = first_status_response.json()["data"]
        assert first_status["status"] == "partial_failed"
        assert first_status["completed_files"] == 1
        assert first_status["failed_files"] == 1

        retry_response = client.post(f"/api/v1/reports/{task_id}/batch/retry-failed")
        assert retry_response.status_code == 200
        assert retry_response.json()["data"]["retry_files"] == 1

        final_status_response = None
        for _ in range(30):
            final_status_response = client.get(f"/api/v1/reports/{task_id}")
            if final_status_response.json()["data"]["status"] != "running":
                break
            time.sleep(0.05)

        results_response = client.get(f"/api/v1/reports/{task_id}/batch-results")

    final_status = final_status_response.json()["data"]
    assert final_status["status"] == "completed"
    assert final_status["completed_files"] == 2
    assert final_status["failed_files"] == 0
    rows = results_response.json()["data"]["items"]
    assert [row["status"] for row in rows] == ["completed", "completed"]


def test_batch_cancel_marks_pending_rows(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, bridge=SlowBridge()) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"placeholder1", "application/vnd.ms-excel")),
                ("files", ("case2.xlsx", b"placeholder2", "application/vnd.ms-excel")),
                ("files", ("case3.xlsx", b"placeholder3", "application/vnd.ms-excel")),
            ],
            data={"project_type": "crc_358_msi"},
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]
        time.sleep(0.05)

        cancel_response = client.delete(f"/api/v1/tasks/{task_id}")
        assert cancel_response.status_code == 200
        time.sleep(0.25)

        status_response = client.get(f"/api/v1/reports/{task_id}")
        results_response = client.get(f"/api/v1/reports/{task_id}/batch-results")

    status = status_response.json()["data"]
    results = results_response.json()["data"]
    assert status["status"] == "cancelled"
    assert status["cancelled_files"] >= 1
    assert results["cancelled_files"] >= 1
    assert "cancelled" in [row["status"] for row in results["items"]]


def test_report_summary_endpoint_reads_sidecar(tmp_path, monkeypatch):
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
        task_id = response.json()["data"]["task_id"]

        summary_response = client.get(f"/api/v1/reports/{task_id}/summary")

    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["schema_version"] == "1.0"
    assert summary["patient"]["sample_id"] == "CASE001"
    assert summary["variants"]["total"] == 1


def test_bridge_infers_crc358_from_project_name_text():
    bridge = ReportGenBridge(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
    )

    result = bridge.infer_project_type_from_text("结直肠癌358基因+MSI")

    assert result["detected"] is True
    assert result["project_type"] == "crc_358_msi"
