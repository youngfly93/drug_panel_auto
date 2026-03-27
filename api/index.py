"""
Vercel serverless entry point.

Wraps the FastAPI app for Vercel's Python runtime.
All /api/* requests route here.
"""

import os
import sys
from pathlib import Path

# ---- Fix paths for Vercel environment ----
# In Vercel, the project root is at /var/task
# We need reportgen, config, templates, data to be importable/findable
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "backend"))

# Set environment variables for the app to find upstream resources within the repo
os.environ.setdefault("RG_WEB_UPSTREAM_ROOT", str(_project_root))
os.environ.setdefault("RG_WEB_STORAGE_ROOT", "/tmp/reportgen_storage")
os.environ.setdefault("RG_WEB_SECRET_KEY", os.environ.get("SECRET_KEY", "vercel-default-key"))

# Ensure /tmp storage dirs exist
for d in ["uploads", "reports", "previews", "db"]:
    os.makedirs(f"/tmp/reportgen_storage/{d}", exist_ok=True)

# Import the FastAPI app
from app.main import create_app  # noqa: E402

app = create_app()

# Vercel handler
handler = app
