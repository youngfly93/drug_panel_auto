"""Clinical info and dynamic form schemas."""

from typing import Any, Optional

from pydantic import BaseModel


class FieldUiHints(BaseModel):
    component: str  # input | input-number | date-picker | switch | select | file-upload
    placeholder: Optional[str] = None
    span: int = 12  # grid span (out of 24)
    options: Optional[list[str]] = None  # for select component
    accept: Optional[str] = None  # for file-upload component


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
    pathology_id: Optional[str] = None
    hospital: Optional[str] = None
    department: Optional[str] = None
    collection_date: Optional[str] = None
    receive_date: Optional[str] = None


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
