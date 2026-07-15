"""Minimal unauthenticated liveness endpoint for infrastructure probes."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Return process liveness without exposing tasks or operational state."""
    return {"status": "ok"}
