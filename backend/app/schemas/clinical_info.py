"""Clinical info and dynamic form schemas."""

from typing import Any, Optional

from pydantic import BaseModel


class FieldUiHints(BaseModel):
    component: str  # input | input-number | date-picker | switch | select | file-upload
    placeholder: Optional[str] = None
    span: int = 12  # grid span (out of 24)
    options: Optional[list[str]] = None  # for select component
    accept: Optional[str] = None  # for file-upload component
    allow_create: bool = False  # for editable select components


class FieldSchema(BaseModel):
    key: str
    label: str
    type: str  # string | int | float | date | bool
    required: bool = False
    default: Optional[Any] = None
    description: Optional[str] = None
    format: Optional[str] = None  # format_template
    synonyms: list[str] = []
    computed: bool = False
    ui: FieldUiHints


class FieldGroup(BaseModel):
    id: str
    label: str
    fields: list[FieldSchema]


class ClinicalFormSchema(BaseModel):
    """Dynamic form schema generated from mapping.yaml."""

    groups: list[FieldGroup]
    project_type: Optional[str] = None


class PatientInfo(BaseModel):
    sample_id: str
    patient_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    cancer_type: Optional[str] = None
    clinical_diagnosis: Optional[str] = None
    pathology_id: Optional[str] = None
    hospital: Optional[str] = None
    department: Optional[str] = None
    sample_type: Optional[str] = None
    sampling_method: Optional[str] = None
    sample_site: Optional[str] = None
    collection_date: Optional[str] = None
    receive_date: Optional[str] = None


class PatientEnrichment(BaseModel):
    sample_id: str
    found: bool = False
    source: Optional[str] = None
    fields: dict[str, Any] = {}
    field_sources: dict[str, str] = {}
    warnings: list[str] = []


class PatientDefaults(BaseModel):
    hospital: Optional[str] = None
    department: Optional[str] = None
    issuer: Optional[str] = None
    reviewer: Optional[str] = None


class ProjectInfo(BaseModel):
    project_name: Optional[str] = None
    detection_method: Optional[str] = None


class SignatureUploadResponse(BaseModel):
    stored_path: str
    original_filename: str
    file_size_bytes: int


class Pdl1ImageUploadResponse(BaseModel):
    """Sanitized, case-specific PD-L1 image upload receipt."""

    stored_path: str
    image_id: str
    uploaded_at: str
    file_size_bytes: int
    width: int
    height: int
