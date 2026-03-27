"""Aggregate all API sub-routers."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.batch import router as batch_router
from app.api.clinical_info import router as clinical_info_router
from app.api.config import router as config_router
from app.api.excel import router as excel_router
from app.api.knowledge import router as knowledge_router
from app.api.report import router as report_router
from app.api.task import router as task_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(excel_router)
api_router.include_router(report_router)
api_router.include_router(batch_router)
api_router.include_router(clinical_info_router)
api_router.include_router(task_router)
api_router.include_router(knowledge_router)
api_router.include_router(config_router)
