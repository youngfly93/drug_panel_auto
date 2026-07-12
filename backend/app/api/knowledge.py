"""Knowledge base browsing endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_admin, require_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import knowledge_service as svc

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/panels", response_model=ApiResponse)
def list_catalog_panels(_user: User = Depends(require_user)):
    """List Panel packages and their reviewed-overlay availability."""
    return ApiResponse(data=svc.get_catalog_panels())


@router.get("/entries", response_model=ApiResponse)
def list_catalog_entries(
    panel_id: str = Query(..., min_length=1, max_length=80),
    kind: Literal["gene", "drug", "targeted_drug"] = Query(...),
    layer: Literal["all", "base", "reviewed_overlay"] = Query("all"),
    search: str = Query("", max_length=100),
    gene: str = Query("", max_length=40),
    review_status: Literal[
        "all",
        "approved_for_runtime",
        "provisional_runtime",
        "legacy_runtime",
        "needs_review",
        "rejected",
        "superseded",
        "not_recorded",
    ] = Query("all"),
    match_scope: Literal["all", "gene", "variant", "event"] = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _user: User = Depends(require_user),
):
    """Browse base and reviewed-overlay entries as separate, typed rows."""
    try:
        data = svc.get_catalog_entries(
            panel_id=panel_id,
            kind=kind,
            layer=layer,
            search=search,
            gene=gene,
            review_status=review_status,
            match_scope=match_scope,
            page=page,
            page_size=page_size,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown panel",
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    return ApiResponse(data=data)


@router.get("/coverage", response_model=ApiResponse)
def catalog_coverage(
    panel_id: str = Query(..., min_length=1, max_length=80),
    _user: User = Depends(require_user),
):
    """Return layer counts and the exact declared coverage denominator."""
    try:
        data = svc.get_catalog_coverage(panel_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown panel",
        ) from None
    return ApiResponse(data=data)


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
