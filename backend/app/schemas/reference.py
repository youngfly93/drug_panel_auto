"""Schemas for reference report management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReferenceReportOut(BaseModel):
    id: str
    panel_id: str
    case_id: str
    name: str
    original_filename: str
    checksum_sha256: str
    active: bool
    formal_golden_verified: bool = False
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReferenceReportList(BaseModel):
    items: list[ReferenceReportOut]
    total: int
