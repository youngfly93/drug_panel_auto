import io
import json
import multiprocessing
import subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from reportgen.models.excel_data import ExcelDataSource  # noqa: E402

from app.api import batch as batch_api  # noqa: E402
from app.api import excel as excel_api  # noqa: E402
from app.api import report as report_api  # noqa: E402
from app.api import task as task_api  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.dependencies import get_bridge, get_current_user  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.services import clinical_info_service as clinical_svc  # noqa: E402
from app.services import generation_preflight  # noqa: E402
from app.services.reportgen_bridge import ReportGenBridge  # noqa: E402

BATCH_TERMINAL_STATUSES = {"completed", "failed", "partial_failed", "cancelled"}


def _wait_for_task_terminal(client, task_id: str, *, attempts: int = 80):
    response = None
    for _ in range(attempts):
        response = client.get(f"/api/v1/reports/{task_id}")
        if response.json()["data"]["status"] in BATCH_TERMINAL_STATUSES:
            return response
        time.sleep(0.05)
    return response


def _synthetic_xlsx_bytes(sample_id: str = "LZ000001") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Meta"
    sheet.append(["样本编号", sample_id])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _slow_enrichment_worker(*_args):
    time.sleep(5)


def test_patient_registry_crud_uses_external_runtime_file(monkeypatch, tmp_path):
    runtime_registry = tmp_path / "runtime" / "patient_info.yaml"
    monkeypatch.setenv("REPORTGEN_PATIENT_INFO_PATH", str(runtime_registry))

    clinical_svc.upsert_patient(
        clinical_svc.PatientInfo(
            sample_id="CASE001",
            patient_name="脱敏测试患者",
            gender="女",
            cancer_type="结直肠癌",
        )
    )

    assert clinical_svc._patient_info_path() == runtime_registry.resolve()
    assert runtime_registry.is_file()
    patient = clinical_svc.get_patient("CASE001")
    assert patient is not None
    assert patient.patient_name == "脱敏测试患者"
    assert patient.gender == "女"


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

    def ensure_project_type_enabled(self, project_type):
        from reportgen.panels.release_scope import ensure_project_type_enabled

        return ensure_project_type_enabled(
            project_type,
            disabled=settings.disabled_project_types,
        )

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
        return {
            "patient_name": "测试患者",
            "sample_id": "CASE001",
            "receive_date": "2026-05-20",
            "report_date": "2026-05-31",
        }

    def generate_report(self, **kwargs):
        self.last_generate_kwargs = kwargs
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = (
            output_dir / f"{Path(kwargs.get('excel_path') or 'fake_report').stem}.docx"
        )
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
        qa_file = output_file.with_suffix(".qa.json")
        qa_file.write_text(
            json.dumps(
                {"status": "PASS", "issues": [], "checks": {}},
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
            "qa_report_file": str(qa_file),
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


class MissingDateBridge(FakeBridge):
    def get_mapped_clinical_fields(self, _excel_data):
        return {"patient_name": "测试患者", "sample_id": "CASE001"}


class SlowBridge(FakeBridge):
    def generate_report(self, **kwargs):
        time.sleep(0.2)
        return super().generate_report(**kwargs)


class CountingBridge(FakeBridge):
    def __init__(self):
        super().__init__()
        self.read_count = 0

    def read_excel(self, excel_path):
        self.read_count += 1
        return super().read_excel(excel_path)


class ConfiguredDateBridge(MissingDateBridge):
    def get_mapped_clinical_fields(self, excel_data):
        fields = super().get_mapped_clinical_fields(excel_data)
        if Path(excel_data.path).stem == "case2":
            fields["collection_date"] = "2026-05-19"
        return fields


class StageBridge(FakeBridge):
    def read_excel(self, excel_path):
        time.sleep(0.12)
        return super().read_excel(excel_path)

    def generate_report(self, **kwargs):
        time.sleep(0.12)
        return super().generate_report(**kwargs)


def _client(tmp_path, monkeypatch, bridge=None, *, role="reviewer"):
    bridge = bridge or FakeBridge()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "patient_enrichment_process_isolation", False)
    monkeypatch.setattr(settings, "patient_enrichment_provider", "generic")
    monkeypatch.setattr(settings, "patient_enrichment_url", "")
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
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        username=f"synthetic-{role}",
        display_name=f"Synthetic {role.title()}",
        role=role,
        is_active=True,
    )
    return TestClient(app)


def _seed_owned_task(task_id: str) -> None:
    db = report_api.SessionLocal()
    try:
        db.add(
            Task(
                id=task_id,
                user_id=1,
                task_type="single",
                status="completed",
            )
        )
        db.commit()
    finally:
        db.close()


def test_report_group_feedback_upload_is_archived_with_metadata(
    tmp_path,
    monkeypatch,
):
    task_id = "synthetic-feedback-task"
    with _client(tmp_path, monkeypatch) as client:
        _seed_owned_task(task_id)
        response = client.post(
            f"/api/v1/reports/{task_id}/feedback",
            files={
                "file": (
                    "review.docx",
                    b"PK\x03\x04synthetic-feedback",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"note": "synthetic regression feedback"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["sample_id"] == task_id
    feedback_dir = tmp_path / "feedback" / task_id
    stored = feedback_dir / payload["filename"]
    assert stored.read_bytes() == b"PK\x03\x04synthetic-feedback"
    metadata = json.loads(
        stored.with_name(stored.name + ".meta.json").read_text(encoding="utf-8")
    )
    assert metadata["sample_id"] == task_id
    assert metadata["task_id"] == task_id
    assert metadata["note"] == "synthetic regression feedback"
    assert metadata["status"] == "new"


def test_report_group_feedback_rejects_unsafe_extension(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/synthetic-feedback-task/feedback",
            files={"file": ("payload.exe", b"synthetic", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert not (tmp_path / "feedback").exists()


def test_report_group_feedback_rejects_oversize_without_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    with _client(tmp_path, monkeypatch) as client:
        _seed_owned_task("synthetic-feedback-task")
        response = client.post(
            "/api/v1/reports/synthetic-feedback-task/feedback",
            files={"file": ("feedback.docx", b"x", "application/octet-stream")},
        )

    assert response.status_code == 413
    assert not any(path.is_file() for path in (tmp_path / "feedback").rglob("*"))


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


def test_inspect_excel_rejects_oversize_upload_and_cleans_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/excel/inspect",
            files={"file": ("case.xlsx", b"x", "application/vnd.ms-excel")},
        )

    assert response.status_code == 413
    assert not list((tmp_path / "uploads").rglob("*.xlsx"))


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
        assert timeout == 2.0
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
    monkeypatch.setattr(
        settings, "patient_enrichment_aes_key", "0123456789abcdef0123456789abcdef"
    )
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


def test_enrichment_transport_fallback_shares_one_deadline(monkeypatch):
    observed = {}

    def slow_urlopen(*_args, **_kwargs):
        time.sleep(0.08)
        raise clinical_svc.urlerror.URLError("synthetic urllib timeout")

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs["timeout"]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(clinical_svc.request, "urlopen", slow_urlopen)
    monkeypatch.setattr(clinical_svc.shutil, "which", lambda _name: "/usr/bin/curl")
    monkeypatch.setattr(clinical_svc.subprocess, "run", fake_run)

    started = time.perf_counter()
    raw, warnings = clinical_svc._post_json_with_curl_fallback(
        "https://example.test/enrich",
        b"{}",
        timeout=0.2,
        source="Synthetic",
    )
    elapsed = time.perf_counter() - started

    max_time_index = observed["command"].index("--max-time") + 1
    curl_budget = float(observed["command"][max_time_index])
    assert raw is None
    assert warnings
    assert 0 < curl_budget <= 0.13
    assert observed["timeout"] <= 0.63
    assert elapsed < 0.5


def test_enrichment_hard_timeout_terminates_child_process(monkeypatch):
    monkeypatch.setattr(settings, "patient_enrichment_process_isolation", True)
    monkeypatch.setattr(
        clinical_svc,
        "_enrich_patient_in_child",
        _slow_enrichment_worker,
    )
    before = {child.pid for child in multiprocessing.active_children()}

    started = time.perf_counter()
    result = clinical_svc.enrich_patient_with_hard_timeout(
        "LZ000001",
        project_type="crc_358_msi",
        timeout_seconds=0.2,
    )
    elapsed = time.perf_counter() - started
    time.sleep(0.1)
    after = {child.pid for child in multiprocessing.active_children()}

    assert elapsed < 1.0
    assert result.found is False
    assert any("exceeded" in warning for warning in result.warnings)
    assert after <= before


def test_enrichment_hard_timeout_returns_fast_child_payload(tmp_path, monkeypatch):
    registry = tmp_path / "patient_info.yaml"
    registry.write_text(
        "patients:\n  LZ000001:\n    patient_name: 合成测试患者\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPORTGEN_PATIENT_INFO_PATH", str(registry))
    monkeypatch.setenv("RG_WEB_PATIENT_ENRICHMENT_PROVIDER", "generic")
    monkeypatch.setenv("RG_WEB_PATIENT_ENRICHMENT_URL", "")
    monkeypatch.setattr(settings, "patient_enrichment_process_isolation", True)

    result = clinical_svc.enrich_patient_with_hard_timeout(
        "LZ000001",
        project_type="crc_358_msi",
        timeout_seconds=3,
    )

    assert result.found is True
    assert result.fields["patient_name"] == "合成测试患者"
    assert result.source == "patient_info"


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
    assert (
        data["output_filename"]
        == "测试患者-癌种未填-结直肠癌358基因+msi-mljy-case001-修改版.docx"
    )
    assert data["output_file_base64"].startswith("UEsD")
    assert data["qa_status"] == "PASS"


def test_crc301_limited_release_blocks_single_and_batch_before_queue(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "disabled_project_types", "crc_301_msi")
    with _client(tmp_path, monkeypatch) as client:
        single = client.post(
            "/api/v1/reports/generate-file-async",
            files={"file": ("case.xlsx", b"placeholder", "application/vnd.ms-excel")},
            data={"clinical_info": "{}", "project_type": "crc_301_msi"},
        )
        batch = client.post(
            "/api/v1/reports/batch-files",
            files=[
                (
                    "files",
                    ("case.xlsx", b"placeholder", "application/vnd.ms-excel"),
                )
            ],
            data={"project_type": "crc_301_msi"},
        )

    assert single.status_code == 409
    assert batch.status_code == 409
    assert "未开放生产生成" in single.json()["detail"]
    assert "未开放生产生成" in batch.json()["detail"]
    db = report_api.SessionLocal()
    try:
        assert db.query(Task).count() == 0
    finally:
        db.close()


def test_crc301_auto_detected_batch_item_stops_before_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "disabled_project_types", "crc_301_msi")
    bridge = FakeBridge()
    bridge.detect_result = {
        "project_type": "crc_301_msi",
        "project_name": "结直肠癌301基因+MSI",
        "confidence": 0.99,
        "detected": True,
    }

    def mapping_must_not_run(_excel_data):
        raise AssertionError("disabled auto-detected panel reached report mapping")

    bridge.get_mapped_clinical_fields = mapping_must_not_run
    try:
        batch_api._prepare_item_clinical_payload(
            stored_path=str(tmp_path / "stored.xlsx"),
            original_filename="case.xlsx",
            bridge=bridge,
            shared_clinical_info={},
            project_type=None,
            project_name=None,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "未开放生产生成" in str(exc.detail)
    else:
        raise AssertionError("auto-detected CRC301 batch item was not rejected")


def test_generate_file_fills_missing_report_date(tmp_path, monkeypatch):
    bridge = MissingDateBridge()
    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
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
    assert response.json()["data"]["success"] is True
    assert (
        bridge.last_generate_kwargs["clinical_info"]["report_date"]
        == date.today().isoformat()
    )


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
                "clinical_info": (
                    '{"patient_name":"测试患者","sample_id":"CASE001",'
                    '"project_name":"结直肠癌358基因+MSI"}'
                ),
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

        status_response = _wait_for_task_terminal(client, data["task_id"])
        download_response = client.get(f"/api/v1/reports/{data['task_id']}/download")

    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["status"] == "completed"
    assert status["output_path"].endswith("case.docx")
    assert status["report_summary_file"].endswith("case.summary.json")
    assert download_response.status_code == 200
    assert download_response.headers["x-reportgen-download-kind"] == "single_docx"
    assert download_response.headers["x-reportgen-task-id"] == data["task_id"]
    assert download_response.headers["x-reportgen-download-retryable"] == "true"
    assert int(download_response.headers["x-reportgen-download-bytes"]) == len(
        download_response.content
    )


def test_reference_gate_required_is_reviewer_only(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, role="operator") as client:
        response = client.post(
            "/api/v1/reports/generate-file-async",
            files={"file": ("case.xlsx", b"placeholder", "application/vnd.ms-excel")},
            data={
                "clinical_info": '{"sample_id":"CASE001"}',
                "project_type": "crc_358_msi",
                "reference_gate_mode": "required",
            },
        )

    assert response.status_code == 403
    assert "金标准验收模式" in response.json()["detail"]


def test_reference_gate_required_forces_full_visual_qa(tmp_path, monkeypatch):
    bridge = FakeBridge()
    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        response = client.post(
            "/api/v1/reports/generate-file",
            files={"file": ("case.xlsx", b"placeholder", "application/vnd.ms-excel")},
            data={
                "clinical_info": '{"sample_id":"CASE001"}',
                "project_type": "crc_358_msi",
                "reference_gate_mode": "required",
                "qa_visual_render": "none",
                "qa_visual_render_required": "false",
            },
        )

    assert response.status_code == 200
    assert bridge.last_generate_kwargs["qa_visual_render"] == "all"
    assert bridge.last_generate_kwargs["qa_visual_render_required"] is True


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

        status_response = _wait_for_task_terminal(client, task_id)

        results_response = client.get(f"/api/v1/reports/{task_id}/batch-results")
        result_rows = results_response.json()["data"]["items"]
        item_response = client.get(result_rows[0]["download_url"])
        zip_response = client.get(f"/api/v1/reports/{task_id}/batch/download")

    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["task_type"] == "batch"
    assert status["status"] == "completed"
    assert status["completed_files"] == 2
    assert status["failed_files"] == 0
    assert results_response.status_code == 200
    rows = result_rows
    assert [row["status"] for row in rows] == ["completed", "completed"]
    assert rows[0]["download_url"].endswith("/batch-results/1/download")
    assert item_response.status_code == 200
    assert item_response.headers["x-reportgen-download-kind"] == "batch_item_docx"
    assert item_response.headers["x-reportgen-task-id"] == task_id
    assert item_response.headers["x-reportgen-download-retryable"] == "true"
    assert int(item_response.headers["x-reportgen-download-bytes"]) == len(
        item_response.content
    )
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"].startswith("application/zip")
    assert zip_response.headers["x-reportgen-download-kind"] == "batch_zip"
    assert zip_response.headers["x-reportgen-task-id"] == task_id
    assert zip_response.headers["x-reportgen-download-retryable"] == "true"
    assert int(zip_response.headers["x-reportgen-download-bytes"]) == len(
        zip_response.content
    )
    assert zip_response.headers["cache-control"] == "private, no-store"
    assert "x-reportgen-prepare-duration-ms" in zip_response.headers
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as zf:
        names = zf.namelist()
    assert "batch_report.json" in names
    assert sum(name.startswith("reports/") for name in names) == 2
    assert sum(name.startswith("summaries/") for name in names) == 2


def test_batch_files_rejects_too_many_files_before_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "max_batch_files", 1)
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"one", "application/vnd.ms-excel")),
                ("files", ("case2.xlsx", b"two", "application/vnd.ms-excel")),
            ],
        )

    assert response.status_code == 413
    assert "最多 1 个" in response.json()["detail"]
    assert not (tmp_path / "uploads").exists()


def test_batch_files_rejects_aggregate_size_and_cleans_saved_files(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(settings, "max_batch_upload_size_mb", 0)
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"one", "application/vnd.ms-excel")),
            ],
        )

    assert response.status_code == 413
    assert "批量文件总大小" in response.json()["detail"]
    assert not list((tmp_path / "uploads").rglob("*.xlsx"))


def test_batch_files_fill_missing_report_date(tmp_path, monkeypatch):
    bridge = MissingDateBridge()
    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"placeholder1", "application/vnd.ms-excel")),
                ("files", ("case2.xlsx", b"placeholder2", "application/vnd.ms-excel")),
            ],
            data={
                "project_type": "crc_358_msi",
                "project_name": "结直肠癌358基因+MSI",
            },
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]

        status_response = _wait_for_task_terminal(client, task_id)

    assert status_response.status_code == 200
    assert status_response.json()["data"]["status"] == "completed"
    assert (
        bridge.last_generate_kwargs["clinical_info"]["report_date"]
        == date.today().isoformat()
    )


def test_batch_files_preflight_uses_sample_enrichment_for_dates(tmp_path, monkeypatch):
    bridge = MissingDateBridge()
    enrich_calls = []

    def fake_enrich_patient(sample_id, project_type=None, **_kwargs):
        enrich_calls.append((sample_id, project_type))
        return SimpleNamespace(fields={"receive_date": "2026-05-20"})

    monkeypatch.setattr(batch_api.clinical_svc, "enrich_patient", fake_enrich_patient)

    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"placeholder1", "application/vnd.ms-excel")),
            ],
            data={
                "project_type": "crc_358_msi",
                "project_name": "结直肠癌358基因+MSI",
                "clinical_info": json.dumps(
                    {"report_date": "2026-05-31"},
                    ensure_ascii=False,
                ),
            },
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]

        status_response = _wait_for_task_terminal(client, task_id)

    assert status_response.status_code == 200
    assert status_response.json()["data"]["status"] == "completed"
    assert ("case1", "crc_358_msi") in enrich_calls
    assert bridge.last_generate_kwargs["clinical_info"]["receive_date"] == "2026-05-20"
    assert bridge.last_generate_kwargs["clinical_info"]["report_date"] == "2026-05-31"


def test_batch_files_ack_is_fast_and_does_not_preflight_synchronously(
    tmp_path,
    monkeypatch,
):
    queued_jobs = []
    enrichment_calls = []
    bridge = CountingBridge()

    monkeypatch.setattr(
        batch_api,
        "submit_generation_job",
        lambda func, *args, **kwargs: queued_jobs.append((func, args, kwargs)),
    )

    def forbidden_enrichment(*_args, **_kwargs):
        enrichment_calls.append(True)
        time.sleep(1)
        raise AssertionError("提交请求不得调用外部富集")

    monkeypatch.setattr(
        batch_api.clinical_svc,
        "enrich_patient_with_hard_timeout",
        forbidden_enrichment,
    )
    payload = _synthetic_xlsx_bytes()
    files = [
        (
            "files",
            (
                f"case{index:02d}.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
        for index in range(1, 15)
    ]

    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        started = time.perf_counter()
        response = client.post(
            "/api/v1/reports/batch-files",
            files=files,
            data={"project_type": "crc_358_msi"},
            headers={"Idempotency-Key": "batch-fast-ack-0001"},
        )
        elapsed = time.perf_counter() - started

    assert response.status_code == 200
    accepted = response.json()["data"]
    assert accepted["status"] == "queued"
    assert accepted["total_files"] == 14
    assert accepted["accept_duration_ms"] < 5000
    assert elapsed < 5
    assert bridge.read_count == 0
    assert enrichment_calls == []
    assert len(queued_jobs) == 1


def test_batch_files_idempotency_contract_and_concurrent_double_click(
    tmp_path,
    monkeypatch,
):
    queued_jobs = []
    monkeypatch.setattr(
        batch_api,
        "submit_generation_job",
        lambda func, *args, **kwargs: queued_jobs.append((func, args, kwargs)),
    )
    body = _synthetic_xlsx_bytes()

    def submit(client, key: str, *, content: bytes = body):
        return client.post(
            "/api/v1/reports/batch-files",
            files=[
                (
                    "files",
                    (
                        "case01.xlsx",
                        content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                )
            ],
            data={"project_type": "crc_358_msi"},
            headers={"Idempotency-Key": key},
        )

    with _client(tmp_path, monkeypatch) as client:
        first = submit(client, "batch-idempotent-0001")
        replay = submit(client, "batch-idempotent-0001")
        conflict = submit(
            client,
            "batch-idempotent-0001",
            content=_synthetic_xlsx_bytes("LZ000002"),
        )
        new_key = submit(client, "batch-idempotent-0002")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(submit, client, "batch-idempotent-race-0003")
                for _ in range(2)
            ]
            concurrent = [future.result() for future in futures]

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["data"]["task_id"] == replay.json()["data"]["task_id"]
    assert replay.json()["data"]["idempotent_replay"] is True
    assert conflict.status_code == 409
    assert new_key.status_code == 200
    assert new_key.json()["data"]["task_id"] != first.json()["data"]["task_id"]
    assert [response.status_code for response in concurrent] == [200, 200]
    assert len({response.json()["data"]["task_id"] for response in concurrent}) == 1
    assert sum(
        not response.json()["data"]["idempotent_replay"]
        for response in concurrent
    ) == 1
    assert len(queued_jobs) == 3


def test_batch_preflight_reuses_one_excel_parse_per_file(tmp_path, monkeypatch):
    bridge = CountingBridge()
    with _client(tmp_path, monkeypatch, bridge=bridge) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                ("files", ("case1.xlsx", b"placeholder1", "application/vnd.ms-excel")),
                ("files", ("case2.xlsx", b"placeholder2", "application/vnd.ms-excel")),
            ],
            data={"project_type": "crc_358_msi"},
        )
        status_response = _wait_for_task_terminal(
            client,
            response.json()["data"]["task_id"],
        )

    assert status_response.json()["data"]["status"] == "completed"
    assert bridge.read_count == 2


def test_batch_configured_required_date_fails_only_affected_file(
    tmp_path,
    monkeypatch,
):
    bridge = ConfiguredDateBridge()
    monkeypatch.setattr(
        generation_preflight,
        "required_date_fields",
        lambda _project_type: [
            ("report_date", "报告日期"),
            ("collection_date", "采样日期"),
        ],
    )

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
        status_response = _wait_for_task_terminal(client, task_id)
        results_response = client.get(f"/api/v1/reports/{task_id}/batch-results")

    status = status_response.json()["data"]
    rows = results_response.json()["data"]["items"]
    assert status["status"] == "partial_failed"
    assert [row["status"] for row in rows] == ["failed", "completed"]
    assert "采样日期" in rows[0]["errors"][0]
    assert "receive_date" not in rows[1]["errors"]
    assert bridge.last_generate_kwargs["clinical_info"]["report_date"] == date.today().isoformat()


def test_batch_status_machine_exposes_all_background_stages(tmp_path, monkeypatch):
    test_client = _client(tmp_path, monkeypatch)
    controlled_stages = ("preflight", "generating", "qa")
    stage_entered = {stage: threading.Event() for stage in controlled_stages}
    stage_release = {stage: threading.Event() for stage in controlled_stages}
    observed_stages = set()
    observed_lock = threading.Lock()
    write_batch_report = batch_api._write_batch_report

    def write_batch_report_with_stage_gate(db, task):
        result = write_batch_report(db, task)
        stage = task.status
        if stage not in stage_entered:
            return result
        with observed_lock:
            first_observation = stage not in observed_stages
            observed_stages.add(stage)
        if first_observation:
            stage_entered[stage].set()
            if not stage_release[stage].wait(timeout=2):
                raise AssertionError(f"timed out waiting to release batch stage: {stage}")
        return result

    monkeypatch.setattr(batch_api, "_write_batch_report", write_batch_report_with_stage_gate)
    with test_client as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[("files", ("case1.xlsx", b"placeholder", "application/vnd.ms-excel"))],
            data={"project_type": "crc_358_msi"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "queued"
        task_id = response.json()["data"]["task_id"]
        observed = ["queued"]
        for stage in controlled_stages:
            assert stage_entered[stage].wait(timeout=2)
            status = client.get(f"/api/v1/reports/{task_id}").json()["data"]["status"]
            observed.append(status)
            stage_release[stage].set()
        final_response = _wait_for_task_terminal(client, task_id)
        observed.append(final_response.json()["data"]["status"])

    assert observed == ["queued", "preflight", "generating", "qa", "completed"]


def test_batch_fourteen_synthetic_files_complete(tmp_path, monkeypatch):
    payload = _synthetic_xlsx_bytes()
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[
                (
                    "files",
                    (
                        f"case{index:02d}.xlsx",
                        payload,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                )
                for index in range(1, 15)
            ],
            data={"project_type": "crc_358_msi"},
        )
        task_id = response.json()["data"]["task_id"]
        status_response = _wait_for_task_terminal(client, task_id, attempts=160)
        results_response = client.get(f"/api/v1/reports/{task_id}/batch-results")

    status = status_response.json()["data"]
    assert status["status"] == "completed"
    assert status["completed_files"] == 14
    assert status["failed_files"] == 0
    assert len(results_response.json()["data"]["items"]) == 14


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

        first_status_response = _wait_for_task_terminal(client, task_id)

        first_status = first_status_response.json()["data"]
        assert first_status["status"] == "partial_failed"
        assert first_status["completed_files"] == 1
        assert first_status["failed_files"] == 1

        retry_response = client.post(f"/api/v1/reports/{task_id}/batch/retry-failed")
        assert retry_response.status_code == 200
        assert retry_response.json()["data"]["retry_files"] == 1

        final_status_response = _wait_for_task_terminal(client, task_id)

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


def test_batch_cancel_during_qa_is_not_overwritten(tmp_path, monkeypatch):
    qa_entered = threading.Event()
    release_qa = threading.Event()
    test_client = _client(tmp_path, monkeypatch, bridge=StageBridge())

    def blocked_diff(*_args, **_kwargs):
        qa_entered.set()
        assert release_qa.wait(timeout=2)
        return {"status": "PASS", "summary": {}}

    monkeypatch.setattr(batch_api.diff_svc, "run_batch_reference_diff", blocked_diff)
    with test_client as client:
        response = client.post(
            "/api/v1/reports/batch-files",
            files=[("files", ("case1.xlsx", b"placeholder", "application/vnd.ms-excel"))],
            data={"project_type": "crc_358_msi"},
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]
        assert qa_entered.wait(timeout=2)
        assert client.get(f"/api/v1/reports/{task_id}").json()["data"]["status"] == "qa"

        cancel_response = client.delete(f"/api/v1/tasks/{task_id}")
        assert cancel_response.status_code == 200
        release_qa.set()
        time.sleep(0.1)

        status = client.get(f"/api/v1/reports/{task_id}").json()["data"]

    assert status["status"] == "cancelled"


def test_task_list_supports_production_filters_and_review_state(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/v1/reports/generate-file",
            files={"file": ("case.xlsx", b"placeholder", "application/vnd.ms-excel")},
            data={"project_type": "crc_358_msi", "clinical_info": "{}"},
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]

        today = datetime.now().date().isoformat()
        draft_response = client.get(
            "/api/v1/tasks",
            params={
                "review_status": "draft",
                "project_type": "crc_358_msi",
                "created_from": today,
                "q": task_id[:8],
            },
        )
        assert draft_response.status_code == 200
        draft_items = draft_response.json()["data"]["items"]
        assert [item["id"] for item in draft_items] == [task_id]
        assert draft_items[0]["review_status"] == "draft"
        assert draft_items[0]["review_status_label"] == "待审核"
        assert draft_items[0]["qa_status"] == "PASS"

        delivered_response = client.post(
            f"/api/v1/reports/{task_id}/review-state",
            json={"status": "delivered", "operator": "qa"},
        )
        assert delivered_response.status_code == 200

        filtered_response = client.get(
            "/api/v1/tasks",
            params={"review_status": "delivered", "qa_status": "PASS"},
        )
        assert filtered_response.status_code == 200
        filtered = filtered_response.json()["data"]
        assert filtered["total"] == 1
        assert filtered["items"][0]["id"] == task_id
        assert filtered["items"][0]["review_status_label"] == "已交付"

        stats_response = client.get("/api/v1/tasks/stats")
        assert stats_response.status_code == 200
        stats = stats_response.json()["data"]
        assert stats["today_total"] >= 1
        assert stats["delivered"] == 1


def test_task_list_attention_filter_surfaces_partial_failed_batch(
    tmp_path, monkeypatch
):
    with _client(tmp_path, monkeypatch, bridge=FailOnceBridge()) as client:
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
        for _ in range(20):
            status = client.get(f"/api/v1/tasks/{task_id}").json()["data"]["status"]
            if status in {"completed", "failed", "partial_failed"}:
                break
            time.sleep(0.05)

        attention_response = client.get("/api/v1/tasks", params={"attention": True})
        assert attention_response.status_code == 200
        items = attention_response.json()["data"]["items"]
        assert task_id in {item["id"] for item in items}
        assert any(item["status"] == "partial_failed" for item in items)


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


def test_uploaded_diff_reference_rejects_oversize_without_partial(tmp_path, monkeypatch):
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
        monkeypatch.setattr(settings, "max_upload_size_mb", 0)
        diff_response = client.post(
            f"/api/v1/reports/{task_id}/diff",
            files={"reference": ("reference.docx", b"x", "application/octet-stream")},
        )

    assert diff_response.status_code == 413
    diff_dir = tmp_path / "reports" / task_id / "report_diff"
    assert not list(diff_dir.rglob("*.part"))
    assert not (diff_dir / "reference.docx").exists()


def test_quality_gate_review_state_and_audit_package(tmp_path, monkeypatch):
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

        gate_response = client.get(f"/api/v1/reports/{task_id}/quality-gate")
        review_response = client.get(f"/api/v1/reports/{task_id}/review-state")
        update_response = client.post(
            f"/api/v1/reports/{task_id}/review-state",
            json={"status": "delivered", "operator": "报告组"},
        )
        audit_response = client.get(f"/api/v1/reports/{task_id}/audit-package")
        audit_log_response = client.get(f"/api/v1/reports/{task_id}/audit-log")

    assert gate_response.status_code == 200
    gate = gate_response.json()["data"]
    assert gate["passed"] is True
    assert gate["blockers"] == 0
    assert any(item["code"] == "DIFF_NOT_RUN" for item in gate["issues"])
    assert review_response.json()["data"]["status"] == "draft"
    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "delivered"
    assert audit_response.status_code == 200
    assert audit_response.headers["content-type"].startswith("application/zip")
    assert audit_log_response.status_code == 200
    audit_log = audit_log_response.json()["data"]["items"]
    actions = {item["action"] for item in audit_log}
    assert "report.generate_file_requested" in actions
    assert "review_state.updated" in actions
    assert "report.download_requested" in actions
    assert all(item["user_id"] == 1 for item in audit_log)
    assert all(item["operator"] == "Synthetic Reviewer" for item in audit_log)
    audit_log_text = audit_log_response.text
    assert "测试患者" not in audit_log_text
    assert "case.xlsx" not in audit_log_text


def test_quality_gate_blocks_failed_batch_delivery(tmp_path, monkeypatch):
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
        task_id = response.json()["data"]["task_id"]

        _wait_for_task_terminal(client, task_id)

        gate_response = client.get(f"/api/v1/reports/{task_id}/quality-gate")
        delivery_response = client.post(
            f"/api/v1/reports/{task_id}/review-state",
            json={"status": "delivered", "operator": "报告组"},
        )

    gate = gate_response.json()["data"]
    assert gate["passed"] is False
    assert any(item["code"] == "BATCH_HAS_FAILURES" for item in gate["issues"])
    assert delivery_response.status_code == 409


def test_bridge_infers_crc358_from_project_name_text():
    bridge = ReportGenBridge(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
    )

    result = bridge.infer_project_type_from_text("结直肠癌358基因+MSI")

    assert result["detected"] is True
    assert result["project_type"] == "crc_358_msi"


def test_bridge_unknown_sample_does_not_inherit_global_project_info(tmp_path):
    """项目识别不得使用 patient_info.yaml 的全局 project_info 兜底。"""

    bridge = ReportGenBridge(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
    )
    excel_path = tmp_path / "CASE-UNKNOWN.xlsx"
    excel_path.write_bytes(b"placeholder")
    excel_data = ExcelDataSource(
        file_path=str(excel_path),
        single_values={"TMB": 7.5},
        table_data={"Variations": []},
        sheet_names=["Variations"],
        metadata={"sample_id_from_filename": "CASE-UNKNOWN"},
    )

    result = bridge.detect_project_type(excel_data.file_path, excel_data=excel_data)

    assert result["detected"] is False
    assert result["project_type"] is None
    assert result["project_name"] is None


def test_download_blocks_qa_fail_but_not_warn_or_missing(tmp_path, monkeypatch):
    """交付门禁（B 步）：QA=FAIL 的报告下载被 409 拦截，需显式 override；
    QA=PASS/WARN 及无 QA 记录的历史任务不被误伤。锁死"下载不查 QA"不会被改回。"""
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    docx = tmp_path / "r.docx"
    docx.write_text("fake")
    qa = tmp_path / "r.qa.json"

    task = SimpleNamespace(
        output_path=str(docx), project_type="crc_358_msi", status="completed"
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = task

    def attempt(qa_status, override=False, role="operator"):
        if qa_status is None:
            if qa.exists():
                qa.unlink()
        else:
            qa.write_text(json.dumps({"status": qa_status, "issues": []}))
        with patch.object(
            report_api, "_observed_file_response", return_value="OK"
        ), patch.object(
            report_api, "_clinical_snapshot", return_value={}
        ), patch.object(
            report_api, "_business_report_filename", return_value="x.docx"
        ):
            try:
                report_api._download_report_response(
                    "t1",
                    db,
                    MagicMock(),
                    SimpleNamespace(id=1, role=role),
                    override_gate=override,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    assert attempt("FAIL") == 409  # QA FAIL → 拦截
    assert attempt("FAIL", override=True) == 403  # 普通操作员不得越权放行
    assert attempt("FAIL", override=True, role="reviewer") == 200
    assert attempt("PASS") == 200  # 正常报告不受影响
    assert attempt("WARN") == 200  # WARN 不拦
    assert attempt(None) == 200  # 无 QA 记录的历史任务不误伤


def test_lung588_controlled_pilot_download_requires_manual_review(tmp_path):
    """肺癌588受控试运行即使 QA=PASS，也必须完成人工复核后才能下载。

    该门禁仅作用于肺癌588，不得误伤现有肠癌生产线。
    """
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    docx = tmp_path / "r.docx"
    docx.write_text("fake")
    docx.with_suffix(".qa.json").write_text(
        json.dumps({"status": "PASS", "issues": []}),
        encoding="utf-8",
    )

    def attempt(project_type, review_status, *, override=False, role="operator"):
        task = SimpleNamespace(
            output_path=str(docx),
            project_type=project_type,
            status="completed",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = task
        with patch.object(
            report_api,
            "_load_review_state",
            return_value={"status": review_status},
        ), patch.object(
            report_api,
            "_observed_file_response",
            return_value="OK",
        ), patch.object(
            report_api,
            "_clinical_snapshot",
            return_value={},
        ), patch.object(
            report_api,
            "_business_report_filename",
            return_value="x.docx",
        ):
            try:
                report_api._download_report_response(
                    "t1",
                    db,
                    MagicMock(),
                    SimpleNamespace(id=1, role=role),
                    override_gate=override,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    assert attempt("lung_588_pdl1", "draft") == 409
    assert attempt("lung_588_pdl1", "reviewed") == 200
    assert attempt("lung_588_pdl1", "delivered") == 200
    assert attempt("lung_588_pdl1", "draft", override=True) == 403
    assert attempt("lung_588_pdl1", "draft", override=True, role="reviewer") == 200
    assert attempt("crc_358_msi", "draft") == 200


def test_batch_item_download_blocks_qa_fail(tmp_path):
    """交付门禁（第3步）：批量逐文件下载与单份一致——QA=FAIL 被 409 拦截、
    override 放行、PASS/WARN/无记录不误伤。"""
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    docx = tmp_path / "r.docx"
    docx.write_text("fake")

    def attempt(qa_status, override=False, role="operator"):
        row = SimpleNamespace(
            output_path=str(docx),
            excel_filename="case01.xlsx",
            validation_summary=(
                json.dumps({"qa_status": qa_status}) if qa_status else "{}"
            ),
        )
        task = SimpleNamespace(task_type="batch")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [task, row]
        with patch.object(report_api, "_observed_file_response", return_value="OK"):
            try:
                report_api.download_batch_item_report(
                    "t1",
                    1,
                    MagicMock(),
                    db=db,
                    override_gate=override,
                    current_user=SimpleNamespace(id=1, role=role),
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    assert attempt("FAIL") == 409
    assert attempt("FAIL", override=True) == 403
    assert attempt("FAIL", override=True, role="reviewer") == 200
    assert attempt("PASS") == 200
    assert attempt("WARN") == 200
    assert attempt(None) == 200
