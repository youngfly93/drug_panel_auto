"""Common response schemas."""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response envelope."""

    success: bool = True
    data: Optional[T] = None
    error: Optional[str] = None


class PaginatedData(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T]
    total: int
    page: int
    page_size: int
