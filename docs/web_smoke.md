# Web Smoke Test

`make web-smoke` runs a local production-style Web API smoke test with a
synthetic workbook. It does not use real patient data.

The smoke test checks:

- built frontend index is served;
- default admin login works in a local test environment;
- synthetic Excel upload succeeds;
- project detection returns `crc_358_msi`;
- sheet list and sheet preview return real row/column data;
- dynamic clinical schema and single-value extraction work;
- report generation completes with `qa_status=PASS`;
- QA endpoint returns `PASS`;
- generated DOCX can be downloaded and contains key expected text.

## Usage

Default:

```bash
make web-smoke
```

This uses the synthetic CRC 358 + MSI workbook by default. It builds the
frontend, starts a local backend on `127.0.0.1:8000` if one is not already
running, executes the smoke flow, and stops the backend it started.

Useful overrides:

```bash
WEB_SMOKE_BUILD=0 make web-smoke
```

Skip frontend build when `backend/static` is already current.

```bash
WEB_SMOKE_PANEL=crc_301_msi WEB_SMOKE_BUILD=0 make web-smoke
```

Run the same Web API flow for the CRC301+MSI panel and its current default
template.

```bash
WEB_SMOKE_PORT=8010 make web-smoke
```

Use a different local port.

```bash
PYTHON=.venv/bin/python make web-smoke
```

Use a specific Python environment.

```bash
WEB_SMOKE_ADMIN_USERNAME=admin WEB_SMOKE_ADMIN_PASSWORD=... make web-smoke
```

Use non-default credentials for staging or production smoke checks.

```bash
WEB_SMOKE_KEEP_SERVER=1 make web-smoke
```

Leave the locally started backend running for manual inspection.

Smoke artifacts are written under:

```text
tmp/web_smoke/
```

This directory is ignored by Git.
