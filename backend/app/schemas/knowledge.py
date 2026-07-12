"""Typed public DTOs for the read-only Panel Knowledge Catalog."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

KnowledgeKind = Literal["gene", "drug", "targeted_drug"]
KnowledgeLayer = Literal["base", "reviewed_overlay"]
KnowledgeMatchScope = Literal["gene", "variant", "event"]
KnowledgeReviewStatus = Literal[
    "approved_for_runtime",
    "provisional_runtime",
    "legacy_runtime",
    "needs_review",
    "rejected",
    "superseded",
    "not_recorded",
]


class KnowledgeReview(BaseModel):
    status: KnowledgeReviewStatus
    scope: str
    basis: str
    runtime_eligible: bool = False
    reviewer: str = ""
    reviewer_type: str = ""
    reviewed_at: str = ""
    evidence_as_of: str = ""
    secondary_review_status: str = ""
    risk_level: str = ""


class KnowledgeProvenance(BaseModel):
    source_id: str
    source_type: str
    source_db: Optional[str] = None
    source_ref: Optional[str] = None
    source_refs: list[dict[str, str]] = Field(default_factory=list)
    sheet: Optional[str] = None
    row_number: Optional[int] = None
    origin_panel_id: Optional[str] = None
    shared_overlay: bool = False
    revision: str
    updated_at: str


class KnowledgeEntry(BaseModel):
    entry_id: str
    kind: KnowledgeKind
    layer: KnowledgeLayer
    panel_id: str
    gene: str
    c_hgvs: str = ""
    p_hgvs: str = ""
    match_scope: KnowledgeMatchScope
    runtime_behavior: str
    review: KnowledgeReview
    provenance: KnowledgeProvenance
    content: dict[str, Any] = Field(default_factory=dict)


class PanelKnowledgeSummary(BaseModel):
    panel_id: str
    display_name: str
    status: str
    overlay_available: bool
    overlay_origin_panel_id: Optional[str] = None
    shared_overlay: bool = False
    review_status: KnowledgeReviewStatus = "not_recorded"
    warning: Optional[str] = None
