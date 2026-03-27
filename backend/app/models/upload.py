"""Upload record ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_names: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    detected_project_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="pending")
