import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.api import knowledge as knowledge_api  # noqa: E402
from app.dependencies import require_user  # noqa: E402


def _client(*, authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_api.router, prefix="/api/v1")
    if authenticated:
        app.dependency_overrides[require_user] = lambda: SimpleNamespace(
            id=1, role="user", is_active=True
        )
    else:

        def reject_user():
            raise HTTPException(status_code=401, detail="Not authenticated")

        app.dependency_overrides[require_user] = reject_user
    return TestClient(app)


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_catalog_requires_login():
    with _client(authenticated=False) as client:
        assert client.get("/api/v1/knowledge/panels").status_code == 401
        assert (
            client.get(
                "/api/v1/knowledge/entries",
                params={"panel_id": "crc_358_msi", "kind": "gene"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/v1/knowledge/coverage",
                params={"panel_id": "crc_358_msi"},
            ).status_code
            == 401
        )


def test_catalog_panels_entries_and_coverage_are_typed_and_sanitized():
    with _client() as client:
        panels_response = client.get("/api/v1/knowledge/panels")
        entries_response = client.get(
            "/api/v1/knowledge/entries",
            params={
                "panel_id": "crc_301_msi",
                "kind": "gene",
                "layer": "reviewed_overlay",
                "page_size": 10,
            },
        )
        coverage_response = client.get(
            "/api/v1/knowledge/coverage",
            params={"panel_id": "crc_301_msi"},
        )
        targeted_response = client.get(
            "/api/v1/knowledge/entries",
            params={
                "panel_id": "crc_301_msi",
                "kind": "targeted_drug",
                "layer": "reviewed_overlay",
                "page_size": 10,
            },
        )
        provisional_response = client.get(
            "/api/v1/knowledge/entries",
            params={
                "panel_id": "crc_358_msi",
                "kind": "gene",
                "layer": "reviewed_overlay",
                "review_status": "provisional_runtime",
                "page_size": 10,
            },
        )

    assert panels_response.status_code == 200
    panels = panels_response.json()["data"]["panels"]
    crc301 = next(row for row in panels if row["panel_id"] == "crc_301_msi")
    assert crc301["shared_overlay"] is True
    assert crc301["overlay_origin_panel_id"] == "crc_358_msi"

    assert entries_response.status_code == 200
    entries = entries_response.json()["data"]
    assert entries["total"] == 797
    assert len(entries["rows"]) == 10
    assert all(row["layer"] == "reviewed_overlay" for row in entries["rows"])
    assert {row["provenance"]["origin_panel_id"] for row in entries["rows"]} == {
        "crc_301_msi",
        "crc_358_msi",
    }

    assert coverage_response.status_code == 200
    coverage = coverage_response.json()["data"]
    assert coverage["declared_gene_coverage"]["denominator_name"] == "reportable_genes"
    assert coverage["declared_gene_coverage"]["total"] == 301
    assert coverage["knowledge_coverage_contract"]["gene_explanation_missing_count"] == 0
    assert (
        coverage["knowledge_coverage_contract"]["drug_candidate_disposition"][
            "pending_medical_review_rows"
        ]
        == 0
    )
    multidimensional = coverage["knowledge_coverage_contract"][
        "multidimensional_coverage"
    ]
    assert multidimensional["review_governance"]["standardized_percent"] == 100.0
    assert multidimensional["source_provenance"]["structured_source_percent"] == 100.0

    assert targeted_response.status_code == 200
    targeted = targeted_response.json()["data"]
    assert targeted["total"] == 9
    assert all(row["kind"] == "targeted_drug" for row in targeted["rows"])

    assert provisional_response.status_code == 200
    provisional = provisional_response.json()["data"]
    assert provisional["total"] == 616
    assert all(
        row["review"]["runtime_eligible"] is True
        and row["provenance"]["source_refs"]
        for row in provisional["rows"]
    )

    serialized = json.dumps(
        {
            "panels": panels_response.json(),
            "entries": entries_response.json(),
            "coverage": coverage_response.json(),
            "targeted": targeted_response.json(),
        },
        ensure_ascii=False,
    )
    assert str(ROOT) not in serialized
    assert "/storage/" not in serialized
    forbidden = {"patient_name", "sample_id", "report_number", "hospital"}
    assert forbidden.isdisjoint(set(_walk_keys(json.loads(serialized))))


def test_catalog_query_boundaries_and_unknown_panel():
    with _client() as client:
        assert (
            client.get(
                "/api/v1/knowledge/entries",
                params={
                    "panel_id": "crc_358_msi",
                    "kind": "gene",
                    "page_size": 101,
                },
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/v1/knowledge/entries",
                params={"panel_id": "../crc_358_msi", "kind": "gene"},
            ).status_code
            == 404
        )


def test_legacy_browse_response_shape_is_preserved():
    with _client() as client:
        stats_response = client.get("/api/v1/knowledge/stats")
        genes_response = client.get(
            "/api/v1/knowledge/genes", params={"page": 1, "page_size": 1}
        )

    assert stats_response.status_code == 200
    stats = stats_response.json()["data"]
    assert set(stats) == {"gene_knowledge", "drug_mappings", "immune_genes"}
    assert genes_response.status_code == 200
    genes = genes_response.json()["data"]
    assert set(genes) == {"columns", "rows", "total", "page", "page_size"}
