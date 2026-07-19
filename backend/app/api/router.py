"""Aggregate public and authenticated API sub-routers."""

from fastapi import APIRouter, Depends

from app.api.auth import router as auth_router
from app.api.batch import router as batch_router
from app.api.clinical_info import router as clinical_info_router
from app.api.config import router as config_router
from app.api.excel import router as excel_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.ops import router as ops_router
from app.api.reference import router as reference_router
from app.api.report import router as report_router
from app.api.task import router as task_router
from app.dependencies import (
    require_admin,
    require_reference_reader,
    require_task_access,
    require_upload_access,
    require_user,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(health_router)

user_dependencies = [Depends(require_user)]
task_dependencies = [Depends(require_task_access)]
upload_dependencies = [Depends(require_upload_access)]
admin_dependencies = [Depends(require_admin)]
reference_dependencies = [Depends(require_reference_reader)]

api_router.include_router(excel_router, dependencies=upload_dependencies)
api_router.include_router(report_router, dependencies=task_dependencies)
api_router.include_router(batch_router, dependencies=task_dependencies)
api_router.include_router(clinical_info_router, dependencies=user_dependencies)
api_router.include_router(task_router, dependencies=task_dependencies)
api_router.include_router(knowledge_router, dependencies=user_dependencies)
api_router.include_router(reference_router, dependencies=reference_dependencies)
api_router.include_router(config_router, dependencies=admin_dependencies)
api_router.include_router(ops_router, dependencies=admin_dependencies)
