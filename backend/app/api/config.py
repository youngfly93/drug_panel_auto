"""Configuration management endpoints."""

from fastapi import APIRouter, Body, Depends, HTTPException

import yaml

from app.dependencies import require_admin
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import config_service as svc

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/files", response_model=ApiResponse)
def list_config_files():
    return ApiResponse(data=svc.list_config_files())


@router.get("/{filename}", response_model=ApiResponse)
def get_config(filename: str):
    try:
        data = svc.get_config(filename)
        return ApiResponse(data=data)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{filename}/raw", response_model=ApiResponse)
def get_config_raw(filename: str):
    try:
        raw = svc.get_config_raw(filename)
        return ApiResponse(data={"filename": filename, "content": raw})
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{filename}", response_model=ApiResponse)
def update_config(
    filename: str,
    content: dict,
    admin: User = Depends(require_admin),
):
    try:
        result = svc.update_config(filename, content)
        if not result["success"]:
            return ApiResponse(success=False, data=result, error="配置校验失败")
        return ApiResponse(data=result)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{filename}/validate", response_model=ApiResponse)
def validate_config(filename: str, content: dict):
    try:
        result = svc.validate_config(filename, content)
        return ApiResponse(data=result)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{filename}/raw", response_model=ApiResponse)
def update_config_raw(
    filename: str,
    raw_content: str = Body(..., media_type="text/plain"),
    admin: User = Depends(require_admin),
):
    """Update config from raw YAML text."""
    try:
        content = yaml.safe_load(raw_content)
        if not isinstance(content, dict):
            return ApiResponse(success=False, error="YAML 必须是字典格式")
        result = svc.update_config(filename, content)
        if not result["success"]:
            return ApiResponse(success=False, data=result, error="配置校验失败")
        return ApiResponse(data=result)
    except yaml.YAMLError as e:
        return ApiResponse(success=False, error=f"YAML 语法错误: {e}")
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{filename}/history", response_model=ApiResponse)
def config_history(filename: str):
    try:
        history = svc.get_config_history(filename)
        return ApiResponse(data=history)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
