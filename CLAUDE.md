# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

基因组Panel自动化系统的 Web 平台，为现有的 Python CLI 报告生成系统（`../基因组panel自动化系统`）提供浏览器端操作界面，将命令行工作流转化为可视化生产流程管理平台。

## Commands

```bash
# Install all dependencies (backend + upstream reportgen + frontend)
make install

# Development: backend (port 8000) + frontend (port 5173) in parallel
make dev

# Backend only
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd frontend && npm run dev

# Build frontend for production (copies dist to backend/static/)
make build

# Run backend tests
cd backend && pytest tests/ -v

# Docker
docker-compose up --build
```

## Architecture

**Tech Stack**: FastAPI + Vue 3 (Composition API) + Element Plus + SQLite (SQLAlchemy) + Pinia + TypeScript

### Backend (`backend/app/`)

- `main.py` — FastAPI app factory with lifespan (creates tables, seeds admin user)
- `config.py` — Settings via pydantic-settings, `RG_WEB_` env prefix
- `database.py` — SQLAlchemy engine + session + `Base`
- `dependencies.py` — DI providers: `get_bridge()`, `get_db()`, JWT auth (`require_user`, `require_admin`)
- `api/` — Route handlers:
  - `excel.py` — Upload, sheet preview, single-values extraction, project type detection
  - `report.py` — Single report generation + download
  - `batch.py` — Batch generation (async via ProcessPoolExecutor)
  - `clinical_info.py` — Dynamic form schema + patient CRUD
  - `knowledge.py` — Gene/drug/immune knowledge base browsing
  - `config.py` — YAML config CRUD with validation + backup + history
  - `task.py` — Task queue list/stats/cancel
  - `auth.py` — JWT login
- `services/` — Business logic:
  - `reportgen_bridge.py` — **Key integration**: directly `import`s upstream `reportgen` package
  - `clinical_info_service.py` — Dynamic form schema from `mapping.yaml` + patient_info.yaml CRUD
  - `task_manager.py` — ProcessPoolExecutor for batch processing
  - `knowledge_service.py` — Wraps gene/drug/immune Excel KBs via pandas
  - `config_service.py` — YAML CRUD with validation, automatic backup, history
  - `file_manager.py` — Upload/storage with path traversal protection
- `models/` — ORM: User, Upload, Task, TaskResult, AuditLog
- `ws/progress.py` — WebSocket for batch progress streaming

### Frontend (`frontend/src/`)

- `api/` — Typed Axios clients: excel, report, clinical, auth, task, knowledge, config
- `composables/useDynamicForm.ts` — **Core**: fetches field schema, manages form state, merge/validate
- `composables/useWebSocket.ts` — Real-time batch progress
- `components/clinical/` — `DynamicClinicalForm.vue` + `FieldRenderer.vue` (schema-driven forms)
- `components/excel/SheetPreview.vue` — Paginated Excel sheet table
- `views/` — 8 pages: Dashboard, ReportGenerate, PatientInfo, KnowledgeBase, ConfigEditor, TaskQueue, Login
- `stores/` — Pinia: auth, excel

### Key Data Flow

```
Upload Excel → ExcelReader.read() → detect project type → fetch dynamic form schema
→ auto-fill form from Excel single_values → user edits → ReportGenerator.generate()
→ docx result → download
```

### Dynamic Clinical Form System

Form schema generated at runtime from upstream `config/mapping.yaml` `single_values`. Each field has `type`, `required`, `default_value`, `synonyms`, `format_template`. Backend groups fields semantically and applies project-type overrides. Fields with `synonyms: []` are computed (read-only).

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/excel/upload` | Upload Excel |
| GET | `/api/v1/excel/{id}/sheets/{name}` | Sheet data (paginated) |
| GET | `/api/v1/clinical-schema` | Dynamic form schema |
| CRUD | `/api/v1/patients` | Patient info management |
| POST | `/api/v1/reports/generate` | Single report |
| POST | `/api/v1/reports/batch` | Batch generation |
| GET | `/api/v1/reports/{id}/download` | Download docx |
| GET | `/api/v1/knowledge/genes` | Gene KB browse |
| GET | `/api/v1/knowledge/drugs` | Drug mappings |
| GET/PUT | `/api/v1/config/{filename}` | Config CRUD |
| GET | `/api/v1/tasks` | Task queue |
| WS | `/ws/tasks/{id}/progress` | Batch progress |

## Upstream System Reference

Backend imports `reportgen` directly from `../基因组panel自动化系统`. Key entry points:
- `ReportGenerator(config_dir, template_dir).generate(...)`
- `ExcelReader(config_dir).read(path)` → `ExcelDataSource`
- `ProjectDetector(config_dir).detect(excel_data)`
- `run_batch_generate_validate(BatchValidateOptions, progress=callback)`
- `GeneKnowledgeProvider(config).load()`

## Data Safety

**Never commit** patient data. `storage/` is gitignored. All `.xlsx`/`.docx` patterns in `.gitignore`.

## Commit Messages

Imperative, scoped: `fix(upload): handle empty fusion sheet`, `feat(api): add batch generation endpoint`
