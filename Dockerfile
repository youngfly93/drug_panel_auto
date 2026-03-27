# Stage 1: Build frontend
FROM node:18-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit
COPY frontend/ .
RUN npm run build

# Stage 2: Production backend + static files
FROM python:3.11-slim AS production

# Install LibreOffice for docx preview (optional, comment out to reduce image size)
# RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-core && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install upstream reportgen
COPY ../基因组panel自动化系统 /upstream
RUN pip install --no-cache-dir -e /upstream

# Install backend
COPY backend/pyproject.toml backend/
RUN pip install --no-cache-dir -e backend/

COPY backend/ backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist backend/static/

# Create storage directories
RUN mkdir -p /app/storage/uploads /app/storage/reports /app/storage/previews /app/storage/db

ENV RG_WEB_UPSTREAM_ROOT=/upstream
ENV RG_WEB_STORAGE_ROOT=/app/storage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
