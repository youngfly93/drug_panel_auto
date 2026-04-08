"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.ws.progress import router as ws_router
from app.config import settings
from app.database import Base, engine
from app.dependencies import pwd_context
from app.models import User  # noqa: F401 — ensure models are registered


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events."""
    # Ensure storage directories exist
    for d in [
        settings.upload_dir,
        settings.report_dir,
        settings.preview_dir,
        settings.signature_dir,
        settings.storage_root / "db",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Security warnings
    import logging
    _log = logging.getLogger("reportgen-web")
    if settings.secret_key == "change-me-in-production":
        _log.warning("⚠ SECRET_KEY is using default value — set RG_WEB_SECRET_KEY for production")
    if settings.default_admin_password == "admin123":
        _log.warning("⚠ Admin password is default 'admin123' — set RG_WEB_DEFAULT_ADMIN_PASSWORD")

    # Seed default admin if no users exist
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                username=settings.default_admin_username,
                password_hash=pwd_context.hash(settings.default_admin_password),
                display_name="管理员",
                role="admin",
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="基因组Panel自动化报告系统",
        description="Genomic panel report automation web platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — restrict in production via RG_WEB_CORS_ORIGINS env var
    import os
    cors_origins = os.environ.get("RG_WEB_CORS_ORIGINS", "").split(",")
    cors_origins = [o.strip() for o in cors_origins if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],  # default "*" only if env not set
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_router)

    # WebSocket routes
    app.include_router(ws_router)

    # Serve frontend static files if built
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
