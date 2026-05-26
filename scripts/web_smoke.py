#!/usr/bin/env python3
"""Local Web API smoke test for the report-generation platform.

The test uses synthetic workbooks, so it is safe to run before release or on a
staging server without exposing patient data.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document  # noqa: E402
from reportgen.core.golden_case import (  # noqa: E402
    build_crc_301_msi_golden_excel,
    build_crc_358_msi_golden_excel,
)


BASE_URL = os.environ.get("WEB_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
OUTPUT_ROOT = Path(
    os.environ.get("WEB_SMOKE_OUTPUT_ROOT", str(ROOT / "tmp" / "web_smoke"))
)
ADMIN_USERNAME = os.environ.get("WEB_SMOKE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("WEB_SMOKE_ADMIN_PASSWORD", "admin123")
TIMEOUT_SECONDS = int(os.environ.get("WEB_SMOKE_TIMEOUT_SECONDS", "240"))
MIN_DOCX_BYTES = int(os.environ.get("WEB_SMOKE_MIN_DOCX_BYTES", "1000000"))
SMOKE_PANEL = os.environ.get("WEB_SMOKE_PANEL", "crc_358_msi")

PANEL_SPECS = {
    "crc_358_msi": {
        "builder": build_crc_358_msi_golden_excel,
        "input_filename": "LZ999001_crc_358_msi_golden.xlsx",
        "project_type": "crc_358_msi",
        "project_name": "结直肠癌358基因+MSI",
        "sample_id": "LZ999001",
        "patient_name": "黄金测试患者",
        "required_text": [
            "本次共检出体细胞变异：2个",
            "与靶向药物用药相关的变异有：1个",
            "微卫星稳定型，MSS",
            "多项临床研究表明，TMB-H的肿瘤",
            "研究表明，MSI-H的实体瘤",
            "ERBB2",
            "c.1979G>A",
            "p.G660D",
        ],
    },
    "crc_301_msi": {
        "builder": build_crc_301_msi_golden_excel,
        "input_filename": "LZ999301_crc_301_msi_golden.xlsx",
        "project_type": "crc_301_msi",
        "project_name": "结直肠癌301基因+MSI",
        "sample_id": "LZ999301",
        "patient_name": "黄金测试患者",
        "required_text": [
            "本次共检出体细胞变异：2个",
            "与靶向药物用药相关的变异有：1个",
            "微卫星稳定型，MSS",
            "多项临床研究表明，TMB-H的肿瘤",
            "研究表明，MSI-H的实体瘤",
            "检测者：",
            "审核者：",
            "ERBB2",
            "c.1979G>A",
            "p.G660D",
        ],
    },
}


class SmokeFailure(RuntimeError):
    """Raised when a smoke-test assertion fails."""


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


def _request(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(
        _url(path),
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return (
                int(response.status),
                response.read(),
                dict(response.headers.items()),
            )
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), dict(exc.headers.items())


def _json_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    status, raw, _headers = _request(
        method,
        path,
        body=body,
        headers=headers,
        timeout=timeout,
    )
    if status < 200 or status >= 300:
        raise SmokeFailure(f"{method} {path} returned HTTP {status}: {raw[:500]!r}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SmokeFailure(f"{method} {path} did not return JSON") from exc
    if data.get("success") is False:
        raise SmokeFailure(f"{method} {path} failed: {data.get('error') or data}")
    return data


def _upload_excel(path: Path) -> dict[str, Any]:
    boundary = f"----reportgen-smoke-{int(time.time() * 1000)}"
    file_bytes = path.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\n'
        ).encode("utf-8"),
        b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n",
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    status, raw, _headers = _request(
        "POST",
        "/api/v1/excel/upload",
        body=b"".join(parts),
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        timeout=120,
    )
    if status < 200 or status >= 300:
        raise SmokeFailure(f"upload returned HTTP {status}: {raw[:500]!r}")
    data = json.loads(raw.decode("utf-8"))
    if not data.get("success"):
        raise SmokeFailure(f"upload failed: {data}")
    return data


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _check_docx_text(path: Path, required_text: list[str]) -> None:
    doc = Document(str(path))
    chunks: list[str] = [p.text for p in doc.paragraphs]
    chunks.extend(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    text = "\n".join(chunks)
    for needle in required_text:
        _assert(needle in text, f"generated DOCX is missing text: {needle}")


def main() -> int:
    started = time.monotonic()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    spec = PANEL_SPECS.get(SMOKE_PANEL)
    if spec is None:
        supported = ", ".join(sorted(PANEL_SPECS))
        raise SmokeFailure(f"unsupported WEB_SMOKE_PANEL={SMOKE_PANEL!r}; choose {supported}")
    print("Web smoke test")
    print(f"  base_url: {BASE_URL}")
    print(f"  panel: {spec['project_type']}")
    print(f"  output_root: {OUTPUT_ROOT}")

    status, body, _headers = _request("GET", "/", timeout=30)
    _assert(status == 200, f"frontend index returned HTTP {status}")
    _assert(
        "基因组Panel自动化报告系统" in body.decode("utf-8", errors="ignore"),
        "frontend index did not contain app title",
    )
    print("  ✅ frontend index")

    login = _json_request(
        "POST",
        "/api/v1/auth/login",
        payload={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    _assert(
        bool((login.get("data") or {}).get("access_token")),
        "admin login did not return a token",
    )
    print("  ✅ auth login")

    stats = _json_request("GET", "/api/v1/tasks/stats", timeout=30)
    _assert(isinstance(stats.get("data"), dict), "task stats payload is invalid")
    print("  ✅ task stats")

    excel_path = spec["builder"](OUTPUT_ROOT / spec["input_filename"])
    upload = _upload_excel(excel_path)
    upload_data = upload["data"]
    upload_id = upload_data["upload_id"]
    _assert(
        upload_data.get("detected_project_type") == spec["project_type"],
        f"expected {spec['project_type']}, got {upload_data.get('detected_project_type')!r}",
    )
    print(f"  ✅ upload + detect ({upload_id})")

    sheets = _json_request("GET", f"/api/v1/excel/{upload_id}/sheets", timeout=30)
    sheet_map = {item["name"]: item for item in sheets["data"]}
    _assert(sheet_map.get("Meta", {}).get("rows") == 1, "Meta sheet row count is wrong")
    _assert(
        sheet_map.get("Meta", {}).get("columns", 0) >= 10,
        "Meta sheet column count is wrong",
    )
    _assert(
        sheet_map.get("Variations", {}).get("rows") == 2,
        "Variations sheet row count is wrong",
    )
    _assert(
        sheet_map.get("Variations", {}).get("columns", 0) >= 10,
        "Variations sheet column count is wrong",
    )
    print("  ✅ sheet list counts")

    meta = _json_request(
        "GET",
        f"/api/v1/excel/{upload_id}/sheets/{urllib.parse.quote('Meta')}?page=1&page_size=5",
        timeout=30,
    )
    _assert(meta["data"]["rows"][0]["样本编号"] == spec["sample_id"], "Meta preview is wrong")
    variations = _json_request(
        "GET",
        f"/api/v1/excel/{upload_id}/sheets/Variations?page=1&page_size=5",
        timeout=30,
    )
    _assert(
        variations["data"]["rows"][0]["Gene_Symbol"] == "ERBB2",
        "Variations preview is wrong",
    )
    print("  ✅ sheet previews")

    schema = _json_request(
        "GET",
        f"/api/v1/clinical-schema?project_type={spec['project_type']}",
        timeout=30,
    )
    _assert(len(schema["data"].get("groups") or []) > 0, "clinical schema is empty")
    single_values = _json_request(
        "GET",
        f"/api/v1/excel/{upload_id}/single-values",
        timeout=30,
    )
    clinical_info = single_values["data"]["fields"]
    _assert(clinical_info.get("sample_id") == spec["sample_id"], "sample_id extraction failed")
    _assert(clinical_info.get("patient_name") == spec["patient_name"], "patient extraction failed")
    print("  ✅ schema + single values")

    generate = _json_request(
        "POST",
        "/api/v1/reports/generate",
        payload={
            "upload_id": upload_id,
            "clinical_info": clinical_info,
            "project_type": spec["project_type"],
            "project_name": spec["project_name"],
            "strict_mode": False,
            "template_contract_mode": "warn",
        },
        timeout=TIMEOUT_SECONDS,
    )
    report_data = generate["data"]
    task_id = report_data["task_id"]
    _assert(report_data["success"] is True, "report generation success flag is false")
    _assert(report_data["qa_status"] == "PASS", f"QA status is {report_data['qa_status']!r}")
    _assert(len(report_data.get("stage_results") or []) > 0, "stage results are missing")
    print(f"  ✅ report generation ({task_id})")

    qa = _json_request("GET", f"/api/v1/reports/{task_id}/qa", timeout=30)
    _assert(qa["data"].get("status") == "PASS", "QA report endpoint did not return PASS")
    print("  ✅ QA endpoint")

    status, raw_docx, _headers = _request(
        "GET",
        f"/api/v1/reports/{task_id}/download",
        timeout=120,
    )
    _assert(status == 200, f"download returned HTTP {status}")
    _assert(len(raw_docx) >= MIN_DOCX_BYTES, f"DOCX is too small: {len(raw_docx)} bytes")
    downloaded = OUTPUT_ROOT / "downloaded.docx"
    downloaded.write_bytes(raw_docx)
    _check_docx_text(downloaded, spec["required_text"])
    print(f"  ✅ download + DOCX text ({len(raw_docx)} bytes)")

    summary = {
        "status": "PASS",
        "base_url": BASE_URL,
        "panel": spec["project_type"],
        "upload_id": upload_id,
        "task_id": task_id,
        "qa_status": report_data["qa_status"],
        "downloaded_docx": str(downloaded),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    report_path = OUTPUT_ROOT / "web_smoke_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  report: {report_path}")
    print("Web smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"Web smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
