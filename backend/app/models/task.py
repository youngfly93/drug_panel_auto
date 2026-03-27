"""Task and TaskResult ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)  # single | batch
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    project_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    template_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    clinical_info_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    # Results
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context_json_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Batch-specific
    total_files: Mapped[int] = mapped_column(Integer, default=1)
    completed_files: Mapped[int] = mapped_column(Integer, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, default=0)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Error info
    errors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class TaskResult(Base):
    __tablename__ = "task_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    file_index: Mapped[int] = mapped_column(Integer, nullable=False)
    excel_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    errors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    validation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
