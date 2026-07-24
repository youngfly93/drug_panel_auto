"""
Clinical info service: dynamic form schema generation + patient_info.yaml CRUD.

Reads mapping.yaml to build the dynamic form schema,
and reads/writes patient_info.yaml for patient management.
"""

import base64
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Optional
from urllib import error as urlerror
from urllib import parse, request

import yaml
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from reportgen.core.signature_library import signature_options

from app.config import settings
from app.schemas.clinical_info import (
    ClinicalFormSchema,
    FieldGroup,
    FieldSchema,
    FieldUiHints,
    PatientDefaults,
    PatientEnrichment,
    PatientInfo,
    ProjectInfo,
)

# File lock for concurrent YAML writes
_yaml_lock = threading.Lock()

# Field grouping rules - maps field keys to semantic groups
FIELD_GROUPS = {
    "demographics": {
        "label": "患者基本信息",
        "fields": [
            "patient_name",
            "gender",
            "age",
            "cancer_type",
            "clinical_diagnosis",
        ],
    },
    "treatment_context": {
        "label": "肺癌治疗适应证上下文",
        "fields": [
            "lung_histology",
            "disease_extent",
            "prior_systemic_therapy",
            "companion_diagnostic_status",
        ],
    },
    "identifiers": {
        "label": "标识信息",
        "fields": ["sample_id", "report_number", "pathology_id"],
    },
    "institution": {
        "label": "送检信息",
        "fields": ["hospital", "department"],
    },
    "temporal": {
        "label": "日期信息",
        "fields": ["collection_date", "receive_date", "report_date"],
    },
    "sample": {
        "label": "样本与项目",
        "fields": [
            "sample_type",
            "sampling_method",
            "sample_site",
            "detection_method",
            "panel_name",
        ],
    },
    "approval": {
        "label": "签发信息",
        "fields": [
            "issuer",
            "reviewer",
            "signature_image_path",
            "detector_signature_image_path",
            "reviewer_signature_image_path",
        ],
    },
    "biomarkers": {
        "label": "检测指标",
        "fields": [
            "msi_status",
            "msi_score",
            "tmb_value",
            "tmb_unit",
            "pdl1_tps",
            "pdl1_cps",
            "pdl1_result",
            "pdl1_assay_profile_id",
            "pdl1_source_record_id",
            "pdl1_source_record_date",
            "pdl1_specimen_id",
            "pdl1_image_disposition",
            "final_conclusion",
        ],
    },
}

ENRICHABLE_FIELDS = {
    "patient_name",
    "gender",
    "age",
    "cancer_type",
    "clinical_diagnosis",
    "pathology_id",
    "hospital",
    "department",
    "sample_type",
    "sampling_method",
    "sample_site",
    "collection_date",
    "receive_date",
    "report_date",
}

ENRICHMENT_KEY_ALIASES = {
    "患者姓名": "patient_name",
    "姓名": "patient_name",
    "病人姓名": "patient_name",
    "性别": "gender",
    "年龄": "age",
    "癌种": "cancer_type",
    "肿瘤类型": "cancer_type",
    "临床诊断": "clinical_diagnosis",
    "诊断": "clinical_diagnosis",
    "病理号": "pathology_id",
    "病理编号": "pathology_id",
    "送检医院": "hospital",
    "医院": "hospital",
    "送检科室": "department",
    "科室": "department",
    "样本类型": "sample_type",
    "标本类型": "sample_type",
    "取材手段": "sampling_method",
    "取样方式": "sampling_method",
    "采样方式": "sampling_method",
    "取材部位": "sample_site",
    "取样部位": "sample_site",
    "采样部位": "sample_site",
    "采样日期": "collection_date",
    "采集日期": "collection_date",
    "接收日期": "receive_date",
    "收样日期": "receive_date",
    "送检日期": "receive_date",
    "报告日期": "report_date",
    "出报告日期": "report_date",
    "userName": "patient_name",
    "sex": "gender",
    "age": "age",
    "cancerName": "clinical_diagnosis",
    "pathologyNumber": "pathology_id",
    "hospital": "hospital",
    "department": "department",
    "sampleType": "sample_type",
    "sampleTime": "collection_date",
    "sampleReachTime": "receive_date",
    "reportDate": "report_date",
    "reportTime": "report_date",
}

MISSING_MARKERS = {"", "-", "--", "未知", "unknown", "none", "null", "nan", "n/a", "na"}
FIELD_MISSING_MARKERS = {
    "hospital": {"某某医院"},
    "department": {"肿瘤科"},
    "sample_type": {"组织"},
}

# Fields hidden from web form (auto-computed or not applicable)
ALWAYS_HIDE = ["project_name"]

# Project-specific field overrides
PROJECT_FIELD_OVERRIDES: dict[str, dict] = {
    "lung_methylation": {
        "show": ["methylation_result"],
        "hide": ALWAYS_HIDE,
        "require": ["methylation_result"],
    },
    "crc_301_msi": {"hide": ALWAYS_HIDE},
    "crc_358_msi": {"hide": ALWAYS_HIDE},
    "lung_329_pdl1": {
        "show": ["pdl1_tps", "pdl1_cps", "pdl1_result"],
        "hide": ALWAYS_HIDE,
    },
    "lung_588_pdl1": {
        "show": [
            "pdl1_tps",
            "pdl1_cps",
            "pdl1_result",
            "pdl1_assay_profile_id",
            "pdl1_source_record_id",
            "pdl1_source_record_date",
            "pdl1_specimen_id",
            "pdl1_image_disposition",
            "lung_histology",
            "disease_extent",
            "prior_systemic_therapy",
            "companion_diagnostic_status",
        ],
        "hide": ALWAYS_HIDE,
        "require": [
            "pdl1_tps",
            "pdl1_cps",
            "pdl1_result",
            "pdl1_assay_profile_id",
            "pdl1_source_record_id",
            "pdl1_source_record_date",
            "pdl1_specimen_id",
            "pdl1_image_disposition",
        ],
    },
    "mlf_result": {"hide": ALWAYS_HIDE},
}

PROJECT_ONLY_FIELDS = {
    "pdl1_tps",
    "pdl1_cps",
    "pdl1_result",
    "pdl1_assay_profile_id",
    "pdl1_source_record_id",
    "pdl1_source_record_date",
    "pdl1_specimen_id",
    "pdl1_image_disposition",
    "methylation_result",
    "lung_histology",
    "disease_extent",
    "prior_systemic_therapy",
    "companion_diagnostic_status",
}

CONTROLLED_FIELD_OPTIONS = {
    "lung_histology": ["非小细胞肺癌", "小细胞肺癌", "其他", "未明确"],
    "disease_extent": [
        "可切除早期",
        "不可切除局部晚期",
        "转移性",
        "未明确",
    ],
    "prior_systemic_therapy": ["已接受", "未接受", "未明确"],
    "companion_diagnostic_status": [
        "已确认符合",
        "待确认",
        "不符合",
    ],
    "pdl1_image_disposition": ["无病例专属图像（报告不展示）"],
}

# UI component mapping by field type
TYPE_TO_COMPONENT = {
    "string": "input",
    "int": "input-number",
    "float": "input-number",
    "date": "date-picker",
    "bool": "switch",
}


def _load_mapping_yaml() -> dict:
    """Load and return the mapping.yaml config."""
    path = Path(settings.upstream_config_dir) / "mapping.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _is_computed_field(field_def: dict) -> bool:
    """Check if a field is computed (empty synonyms and not required from user)."""
    synonyms = field_def.get("synonyms", [])
    return isinstance(synonyms, list) and len(synonyms) == 0


def _runtime_pdl1_profile_ids() -> list[str]:
    """Return PD-L1 profiles enabled for the current release tier."""

    try:
        from reportgen.panels.loader import PanelPackageLoader
        from reportgen.rules.pdl1 import is_pdl1_profile_runtime_allowed
        from reportgen.rules.schema import load_rule_yaml

        package = PanelPackageLoader(project_root=settings.upstream_root).load("lung_588_pdl1")
        contract = load_rule_yaml(package.resolve_rule_file("pdl1_product_contract"))
    except Exception:
        return []

    approved: list[str] = []
    for profile in contract.get("candidate_profiles") or []:
        if not isinstance(profile, dict):
            continue
        profile_id = str(profile.get("profile_id") or "").strip()
        if is_pdl1_profile_runtime_allowed(profile, contract):
            approved.append(profile_id)
    return sorted(approved)


def _build_ui_hints(key: str, field_def: dict) -> FieldUiHints:
    """Build UI hints for a field."""
    if key == "signature_image_path" or key.endswith("_signature_image_path"):
        placeholder = "请选择或上传签名图片"
        if key in {"detector_signature_image_path", "reviewer_signature_image_path"}:
            placeholder = "可选：上传临时签名图片，优先级高于签名库"
        return FieldUiHints(
            component="file-upload",
            placeholder=placeholder,
            span=24,
            accept=".png,.jpg,.jpeg,.webp",
        )
    if key in {"issuer", "reviewer"}:
        role = "detector" if key == "issuer" else "reviewer"
        options = signature_options(settings.upstream_config_dir, role)
        return FieldUiHints(
            component="select" if options else "input",
            placeholder="请选择或输入人员姓名",
            span=12,
            options=options,
            allow_create=True,
        )
    if key == "pdl1_result":
        return FieldUiHints(
            component="select",
            placeholder="请选择PD-L1结果分层",
            span=12,
            options=["阳性（高表达）", "阳性（低表达）", "阴性"],
        )
    if key == "pdl1_assay_profile_id":
        options = _runtime_pdl1_profile_ids()
        return FieldUiHints(
            component="select",
            placeholder=(
                "请选择PD-L1检测/转录方案" if options else "暂无经报告组二审的PD-L1检测方案"
            ),
            span=12,
            options=options,
        )
    if key in CONTROLLED_FIELD_OPTIONS:
        return FieldUiHints(
            component="select",
            placeholder=f"请选择{field_def.get('description', key)}",
            span=12,
            options=CONTROLLED_FIELD_OPTIONS[key],
        )

    ftype = field_def.get("type", "string")
    component = TYPE_TO_COMPONENT.get(ftype, "input")
    desc = field_def.get("description", "")

    # Determine grid span based on type
    if ftype == "date":
        span = 8
    elif ftype in ("int", "float"):
        span = 6
    elif ftype == "bool":
        span = 4
    else:
        span = 12

    return FieldUiHints(
        component=component,
        placeholder=f"请输入{desc}" if desc else None,
        span=span,
    )


def get_clinical_form_schema(project_type: Optional[str] = None) -> ClinicalFormSchema:
    """
    Generate a dynamic form schema from mapping.yaml single_values.

    Groups fields semantically, marks computed fields as readonly,
    and applies project-type-specific overrides.
    """
    mapping = _load_mapping_yaml()
    single_values = mapping.get("single_values", {})

    # Build all field schemas
    all_fields: dict[str, FieldSchema] = {}
    for key, field_def in single_values.items():
        if not isinstance(field_def, dict):
            continue
        computed = _is_computed_field(field_def)
        # First synonym as label, fallback to key
        synonyms = field_def.get("synonyms", [])
        label = synonyms[0] if synonyms else key

        all_fields[key] = FieldSchema(
            key=key,
            label=label,
            type=field_def.get("type", "string"),
            required=field_def.get("required", False),
            default=field_def.get("default_value"),
            description=field_def.get("description"),
            format=field_def.get("format_template"),
            synonyms=synonyms,
            computed=computed,
            ui=_build_ui_hints(key, field_def),
        )

    # Apply project-type overrides
    overrides = PROJECT_FIELD_OVERRIDES.get(project_type, {}) if project_type else {}
    show_fields = set(overrides.get("show", []))
    hide_fields = set(overrides.get("hide", [])) | (PROJECT_ONLY_FIELDS - show_fields)
    require_fields = set(overrides.get("require", []))
    for key in require_fields:
        if key in all_fields:
            all_fields[key].required = True

    # Assign fields to groups
    assigned = set()
    groups: list[FieldGroup] = []

    for group_id, group_def in FIELD_GROUPS.items():
        fields = []
        for fkey in group_def["fields"]:
            if fkey in all_fields and fkey not in hide_fields:
                fields.append(all_fields[fkey])
                assigned.add(fkey)
        if fields:
            groups.append(FieldGroup(id=group_id, label=group_def["label"], fields=fields))

    # Computed fields group (readonly)
    computed_fields = [
        f
        for k, f in all_fields.items()
        if k not in assigned and f.computed and k not in hide_fields
    ]
    if computed_fields:
        groups.append(FieldGroup(id="computed", label="计算字段(只读)", fields=computed_fields))
        assigned.update(f.key for f in computed_fields)

    # Catch-all for unassigned non-computed fields
    other_fields = [f for k, f in all_fields.items() if k not in assigned and k not in hide_fields]
    if other_fields:
        groups.append(FieldGroup(id="other", label="其他", fields=other_fields))

    return ClinicalFormSchema(groups=groups, project_type=project_type)


# ---- patient_info.yaml CRUD ----


def _patient_info_path() -> Path:
    # Patient data is runtime state and must not be written into an immutable
    # release checkout.  The start script points this at
    # ``$STORAGE_DIR/patient_info.yaml`` in production; the repository config
    # remains a development/default fallback only.
    override = str(os.environ.get("REPORTGEN_PATIENT_INFO_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(settings.upstream_config_dir) / "patient_info.yaml"


def _load_patient_info() -> dict:
    path = _patient_info_path()
    if not path.exists():
        return {"patients": {}, "defaults": {}, "project_info": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"patients": {}, "defaults": {}, "project_info": {}}


def _save_patient_info(data: dict) -> None:
    with _yaml_lock:
        path = _patient_info_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)


def list_patients() -> list[PatientInfo]:
    data = _load_patient_info()
    patients = data.get("patients", {})
    result = []
    for sample_id, info in patients.items():
        result.append(
            PatientInfo(
                sample_id=str(sample_id),
                **{key: str(value) if value else None for key, value in info.items()},
            )
        )
    return result


def get_patient(sample_id: str) -> Optional[PatientInfo]:
    data = _load_patient_info()
    patients = data.get("patients", {})
    info = patients.get(sample_id)
    if info is None:
        return None
    return PatientInfo(sample_id=sample_id, **{k: str(v) if v else None for k, v in info.items()})


def enrich_patient(
    sample_id: str,
    project_type: Optional[str] = None,
    *,
    timeout_seconds: Optional[float] = None,
) -> PatientEnrichment:
    """
    Enrich clinical fields by sample_id.

    Source order:
    1. local patient_info.yaml registry;
    2. optional external operation-system API configured with
       RG_WEB_PATIENT_ENRICHMENT_URL.

    This function never embeds patient data in code. Real patient values must
    come from runtime storage or the external registry.
    """
    sample_id = str(sample_id or "").strip()
    if not sample_id:
        return PatientEnrichment(sample_id="", warnings=["sample_id is empty"])

    warnings: list[str] = []
    fields: dict[str, Any] = {}
    field_sources: dict[str, str] = {}

    local_fields = _patient_fields_from_local_registry(sample_id)
    if local_fields:
        _merge_enrichment_fields(
            fields,
            field_sources,
            local_fields,
            source="patient_info",
            overwrite=False,
        )

    external_fields, external_source, external_warnings = _fetch_external_patient(
        sample_id,
        project_type=project_type,
        timeout_seconds=timeout_seconds,
    )
    warnings.extend(external_warnings)
    if external_fields:
        _merge_enrichment_fields(
            fields,
            field_sources,
            external_fields,
            source=external_source or settings.patient_enrichment_source_name,
            overwrite=True,
        )

    source = None
    if fields:
        sources = set(field_sources.values())
        source = "mixed" if len(sources) > 1 else next(iter(field_sources.values()))

    return PatientEnrichment(
        sample_id=sample_id,
        found=bool(fields),
        source=source,
        fields=fields,
        field_sources=field_sources,
        warnings=warnings,
    )


def merge_enrichment_into_values(
    values: dict[str, Any],
    enrichment: PatientEnrichment,
) -> dict[str, Any]:
    """Return values + enrichment, filling only missing placeholder fields."""
    merged = dict(values or {})
    for key, value in enrichment.fields.items():
        if _is_missing_value(merged.get(key), field=key):
            merged[key] = value
    return merged


def project_code_from_filename(filename: Optional[str]) -> str:
    """Return the upload filename stem used by the external ops registry."""
    name = Path(str(filename or "")).name.strip()
    if not name:
        return ""
    return Path(name).stem.strip()


def fill_missing_report_date(values: dict[str, Any]) -> dict[str, Any]:
    """Return values with report_date filled by the generation date when absent."""
    filled = dict(values or {})
    if _is_missing_value(filled.get("report_date")):
        filled["report_date"] = date.today().isoformat()
    return filled


def _patient_fields_from_local_registry(sample_id: str) -> dict[str, Any]:
    data = _load_patient_info()
    patients = data.get("patients", {}) or {}
    info = patients.get(sample_id)
    if info is None:
        normalized = sample_id.upper()
        for key, value in patients.items():
            if str(key).upper() == normalized:
                info = value
                break
    return _normalize_patient_payload(info or {})


def _fetch_external_patient(
    sample_id: str,
    project_type: Optional[str] = None,
    *,
    timeout_seconds: Optional[float] = None,
) -> tuple[dict[str, Any], Optional[str], list[str]]:
    provider = str(settings.patient_enrichment_provider or "generic").strip().lower()
    if provider == "marvelbio":
        return _fetch_marvelbio_patient(
            sample_id,
            timeout_seconds=timeout_seconds,
        )

    url = str(settings.patient_enrichment_url or "").strip()
    if not url:
        return {}, None, []

    params = {"sample_id": sample_id}
    if project_type:
        params["project_type"] = project_type
    if "{sample_id}" in url:
        endpoint = url.format(sample_id=parse.quote(sample_id))
        if project_type:
            separator = "&" if "?" in endpoint else "?"
            endpoint = f"{endpoint}{separator}{parse.urlencode({'project_type': project_type})}"
    else:
        separator = "&" if "?" in url else "?"
        endpoint = f"{url}{separator}{parse.urlencode(params)}"

    headers = {"Accept": "application/json"}
    if settings.patient_enrichment_token:
        headers["Authorization"] = f"Bearer {settings.patient_enrichment_token}"

    req = request.Request(endpoint, headers=headers, method="GET")
    timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else settings.patient_enrichment_timeout_seconds
    )
    try:
        with request.urlopen(
            req,
            timeout=max(0.1, timeout),
        ) as response:
            raw = response.read().decode("utf-8")
    except (urlerror.URLError, TimeoutError, OSError) as exc:
        return {}, None, [f"patient enrichment lookup failed: {exc}"]

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, None, [f"patient enrichment returned invalid JSON: {exc}"]

    source = None
    if isinstance(payload, dict):
        source = str(payload.get("source") or "").strip() or None
        if payload.get("success") is False:
            message = str(payload.get("error") or payload.get("message") or "lookup failed")
            return {}, source, [message]
        payload = payload.get("data") or payload.get("patient") or payload.get("fields") or payload

    return _normalize_patient_payload(payload), source, []


def _fetch_marvelbio_patient(
    sample_id: str,
    *,
    timeout_seconds: Optional[float] = None,
) -> tuple[dict[str, Any], Optional[str], list[str]]:
    url = str(settings.patient_enrichment_url or "").strip()
    aes_key = str(settings.patient_enrichment_aes_key or "")
    encrypt_flag = str(settings.patient_enrichment_encrypt_flag or "").strip()
    if not url:
        return {}, None, []
    if not aes_key or not encrypt_flag:
        return {}, "marvelbio", ["MarvelBio enrichment is missing AES key or encrypt flag"]

    try:
        encrypt_code = _aes_cbc_pkcs5_base64(sample_id, aes_key)
    except ValueError as exc:
        return {}, "marvelbio", [str(exc)]

    body = json.dumps(
        {
            "encryptCode": encrypt_code,
            "encryptFlag": encrypt_flag,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    raw, lookup_warnings = _post_json_with_curl_fallback(
        url,
        body,
        timeout=float(
            timeout_seconds
            if timeout_seconds is not None
            else settings.patient_enrichment_timeout_seconds
        ),
        source="MarvelBio",
    )
    if raw is None:
        return {}, "marvelbio", lookup_warnings

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, "marvelbio", [f"MarvelBio enrichment returned invalid JSON: {exc}"]

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return {}, "marvelbio", ["MarvelBio enrichment returned unexpected payload"]

    status = str(result.get("status") or "").strip()
    if status and status != "200":
        message = str(result.get("message") or "lookup failed")
        return {}, "marvelbio", [f"MarvelBio enrichment failed: {message}"]

    data = result.get("data") or {}
    fields = _normalize_patient_payload(data)
    if isinstance(data, dict) and not _is_missing_value(data.get("cancerName")):
        cancer_name = data.get("cancerName")
        fields.setdefault("cancer_type", cancer_name)
        fields.setdefault("clinical_diagnosis", cancer_name)
    return fields, "marvelbio", []


def _post_json_with_curl_fallback(
    url: str,
    body: bytes,
    *,
    timeout: float,
    source: str,
) -> tuple[Optional[str], list[str]]:
    """POST JSON within one shared wall-clock budget across both transports."""
    total_budget = max(0.1, float(timeout))
    deadline = time.monotonic() + total_budget
    req = request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
            "User-Agent": "ReportGen-Web/clinical-enrichment",
        },
        method="POST",
    )
    # Keep enough of the one total budget for curl, whose --max-time is a real
    # wall-clock cap and works around urllib/TLS incompatibilities seen in prod.
    urllib_budget = min(total_budget, max(0.1, total_budget * 0.4))
    try:
        with request.urlopen(req, timeout=urllib_budget) as response:
            return response.read().decode("utf-8"), []
    except (urlerror.URLError, TimeoutError, OSError) as exc:
        urllib_error = str(exc)

    curl = shutil.which("curl")
    if not curl:
        return None, [f"{source} enrichment lookup failed: {urllib_error}"]

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, [f"{source} enrichment lookup failed within {total_budget:g}s: {urllib_error}"]

    try:
        completed = subprocess.run(
            [
                curl,
                "-ksS",
                "--connect-timeout",
                f"{max(0.1, min(remaining, remaining * 0.5)):.3f}",
                "--max-time",
                f"{max(0.1, remaining):.3f}",
                "-H",
                "Accept: application/json",
                "-H",
                "Content-Type: application/json",
                "-X",
                "POST",
                "--data-binary",
                "@-",
                url,
            ],
            input=body,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(0.2, remaining + 0.5),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, [
            f"{source} enrichment lookup failed: {urllib_error}; curl fallback failed: {exc}"
        ]

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="ignore").strip()
        return None, [
            f"{source} enrichment lookup failed: {urllib_error}; "
            f"curl fallback failed: {stderr or completed.returncode}"
        ]
    return completed.stdout.decode("utf-8", errors="ignore"), []


def _enrich_patient_in_child(
    sample_id: str,
    project_type: Optional[str],
    timeout_seconds: float,
) -> PatientEnrichment:
    return enrich_patient(
        sample_id,
        project_type=project_type,
        timeout_seconds=timeout_seconds,
    )


def enrich_patient_with_hard_timeout(
    sample_id: str,
    project_type: Optional[str] = None,
    *,
    timeout_seconds: Optional[float] = None,
) -> PatientEnrichment:
    """Return enrichment within a killable total deadline for batch workers."""
    hard_timeout = max(
        0.1,
        float(
            timeout_seconds
            if timeout_seconds is not None
            else settings.patient_enrichment_hard_timeout_seconds
        ),
    )
    if not settings.patient_enrichment_process_isolation:
        return enrich_patient(
            sample_id,
            project_type=project_type,
            timeout_seconds=hard_timeout,
        )

    from app.services.generation_process import (
        GenerationProcessError,
        GenerationTimeoutError,
        run_callable_with_timeout,
    )

    try:
        result = run_callable_with_timeout(
            _enrich_patient_in_child,
            args=(sample_id, project_type, hard_timeout),
            timeout_seconds=hard_timeout,
            grace_seconds=0.25,
        )
    except GenerationTimeoutError:
        return PatientEnrichment(
            sample_id=sample_id,
            warnings=[f"patient enrichment exceeded {hard_timeout:g}s and was skipped"],
        )
    except GenerationProcessError as exc:
        return PatientEnrichment(
            sample_id=sample_id,
            warnings=[f"patient enrichment failed and was skipped: {exc}"],
        )
    return (
        result
        if isinstance(result, PatientEnrichment)
        else PatientEnrichment(
            sample_id=sample_id,
            warnings=["patient enrichment returned an invalid result and was skipped"],
        )
    )


def _aes_cbc_pkcs5_base64(text: str, key: str) -> str:
    key_bytes = key.encode("utf-8")
    if len(key_bytes) not in {16, 24, 32}:
        raise ValueError("MarvelBio AES key must be 16, 24, or 32 bytes")
    iv = key_bytes[:16]
    data = str(text).encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len]) * pad_len
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def _normalize_patient_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    fields: dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = ENRICHMENT_KEY_ALIASES.get(str(raw_key), str(raw_key))
        if key not in ENRICHABLE_FIELDS:
            continue
        if _is_missing_value(value):
            continue
        fields[key] = value
    return fields


def _merge_enrichment_fields(
    target: dict[str, Any],
    field_sources: dict[str, str],
    incoming: dict[str, Any],
    *,
    source: str,
    overwrite: bool,
) -> None:
    for key, value in incoming.items():
        if key not in ENRICHABLE_FIELDS or _is_missing_value(value):
            continue
        if overwrite or _is_missing_value(target.get(key)):
            target[key] = value
            field_sources[key] = source


def _is_missing_value(value: Any, field: Optional[str] = None) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    text = str(value).strip()
    if text.lower() in MISSING_MARKERS:
        return True
    if field and text in FIELD_MISSING_MARKERS.get(field, set()):
        return True
    return False


def upsert_patient(patient: PatientInfo) -> None:
    data = _load_patient_info()
    if "patients" not in data:
        data["patients"] = {}
    entry = patient.model_dump(exclude={"sample_id"}, exclude_none=True)
    data["patients"][patient.sample_id] = entry
    _save_patient_info(data)


def delete_patient(sample_id: str) -> bool:
    data = _load_patient_info()
    patients = data.get("patients", {})
    if sample_id in patients:
        del patients[sample_id]
        _save_patient_info(data)
        return True
    return False


def get_defaults() -> PatientDefaults:
    data = _load_patient_info()
    defaults = data.get("defaults", {})
    return PatientDefaults(**defaults)


def update_defaults(defaults: PatientDefaults) -> None:
    data = _load_patient_info()
    data["defaults"] = defaults.model_dump(exclude_none=True)
    _save_patient_info(data)


def get_project_info() -> ProjectInfo:
    data = _load_patient_info()
    pi = data.get("project_info", {})
    return ProjectInfo(**pi)


def update_project_info(info: ProjectInfo) -> None:
    data = _load_patient_info()
    data["project_info"] = info.model_dump(exclude_none=True)
    _save_patient_info(data)
