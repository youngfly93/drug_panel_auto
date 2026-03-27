"""Knowledge base browsing endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_admin
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import knowledge_service as svc

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/genes", response_model=ApiResponse)
def list_genes(
    search: str = Query("", description="Search keyword"),
    page: int = 1,
    page_size: int = 50,
):
    data = svc.get_gene_list(page=page, page_size=page_size, search=search)
    return ApiResponse(data=data)


@router.get("/genes/{gene_name}", response_model=ApiResponse)
def get_gene_detail(gene_name: str):
    data = svc.get_gene_detail(gene_name)
    if not data.get("sheets"):
        return ApiResponse(success=False, error=f"未找到基因: {gene_name}")
    return ApiResponse(data=data)


@router.get("/drugs", response_model=ApiResponse)
def list_drugs(
    search: str = Query("", description="Search keyword"),
    page: int = 1,
    page_size: int = 50,
):
    data = svc.get_drug_list(page=page, page_size=page_size, search=search)
    return ApiResponse(data=data)


@router.get("/immune-genes", response_model=ApiResponse)
def list_immune_genes():
    data = svc.get_immune_genes()
    return ApiResponse(data=data)


@router.get("/stats", response_model=ApiResponse)
def knowledge_stats():
    data = svc.get_stats()
    return ApiResponse(data=data)


@router.post("/reload", response_model=ApiResponse)
def reload_knowledge_bases(admin: User = Depends(require_admin)):
    """Force reload all knowledge base caches (admin only)."""
    svc.reload_all()
    return ApiResponse(data={"reloaded": True})
