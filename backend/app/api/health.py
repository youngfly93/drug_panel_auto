"""Anonymous liveness probe for deploy and watchdog health gates."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Return process liveness without querying storage or exposing task state."""
    return {"status": "ok"}
