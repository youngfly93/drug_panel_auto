"""Clinical info schema and patient management endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.schemas.clinical_info import (
    ClinicalFormSchema,
    PatientDefaults,
    PatientInfo,
    ProjectInfo,
)
from app.schemas.common import ApiResponse
from app.services import clinical_info_service as svc

router = APIRouter(tags=["clinical-info"])


# ---- Dynamic Form Schema ----

@router.get("/clinical-schema", response_model=ApiResponse[ClinicalFormSchema])
def get_clinical_schema(project_type: Optional[str] = None):
    """Get dynamic form schema adapted to project type."""
    schema = svc.get_clinical_form_schema(project_type)
    return ApiResponse(data=schema)


# ---- Patient CRUD ----

@router.get("/patients", response_model=ApiResponse[list[PatientInfo]])
def list_patients():
    return ApiResponse(data=svc.list_patients())


@router.get("/patients/defaults", response_model=ApiResponse[PatientDefaults])
def get_defaults():
    return ApiResponse(data=svc.get_defaults())


@router.put("/patients/defaults", response_model=ApiResponse[PatientDefaults])
def update_defaults(defaults: PatientDefaults):
    svc.update_defaults(defaults)
    return ApiResponse(data=defaults)


@router.get("/patients/project-info", response_model=ApiResponse[ProjectInfo])
def get_project_info():
    return ApiResponse(data=svc.get_project_info())


@router.put("/patients/project-info", response_model=ApiResponse[ProjectInfo])
def update_project_info(info: ProjectInfo):
    svc.update_project_info(info)
    return ApiResponse(data=info)


@router.get("/patients/{sample_id}", response_model=ApiResponse[PatientInfo])
def get_patient(sample_id: str):
    patient = svc.get_patient(sample_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="患者记录不存在")
    return ApiResponse(data=patient)


@router.post("/patients", response_model=ApiResponse[PatientInfo])
def create_patient(patient: PatientInfo):
    existing = svc.get_patient(patient.sample_id)
    if existing:
        raise HTTPException(status_code=409, detail="样本编号已存在")
    svc.upsert_patient(patient)
    return ApiResponse(data=patient)


@router.put("/patients/{sample_id}", response_model=ApiResponse[PatientInfo])
def update_patient(sample_id: str, patient: PatientInfo):
    patient.sample_id = sample_id
    svc.upsert_patient(patient)
    return ApiResponse(data=patient)


@router.delete("/patients/{sample_id}", response_model=ApiResponse)
def delete_patient(sample_id: str):
    if not svc.delete_patient(sample_id):
        raise HTTPException(status_code=404, detail="患者记录不存在")
    return ApiResponse(data=None)
