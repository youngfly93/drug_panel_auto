from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_checklist_uses_real_iyun129_topology() -> None:
    checklist = _read("docs/release_checklist.md")
    operational = checklist.split("## 3. Deploy", 1)[1]

    assert "scripts/iyun129_deploy_clean.sh" in operational
    assert "scripts/iyun129_release.sh status" in operational
    assert "scripts/iyun129_release.sh rollback" in operational
    assert "/media/desk16/iy12922/apps/reportgen-web-releases" in operational
    assert "127.0.0.1:18082" in operational
    assert "systemctl status reportgen-web" not in operational
    assert "/opt/reportgen-web" not in operational
    assert "127.0.0.1:8000" not in operational


def test_iyun129_wrapper_pins_production_coordinates() -> None:
    wrapper = _read("scripts/iyun129_deploy_clean.sh")
    limited_release_panels = "crc_301_msi,lung_methylation"

    assert "SSH_HOST:-iyun129" in wrapper
    assert "/media/desk16/iy12922/apps" in wrapper
    assert "PORT:-18082" in wrapper
    assert "MANAGE_TUNNEL:-0" in wrapper
    assert "UPLOAD_MAINTENANCE_SCRIPTS:-0" in wrapper
    assert "UPLOAD_ALERTS_SCRIPT:-1" in wrapper
    assert "UPLOAD_CLOUDFLARED_SCRIPTS:-1" in wrapper
    assert "/api/v1/healthz" in wrapper
    assert "RG_WEB_DOCS_ENABLED" in wrapper
    assert "SYNC_SIGNATURE_ASSETS:-1" in wrapper
    assert "SIGNATURE_ASSET_DIR:-storage/signatures" in wrapper
    assert "REQUIRE_HISTORICAL_GOLDEN:-1" in wrapper
    assert ".work/historical_golden_release_manifest.yaml" in wrapper
    assert "RUN_REMOTE_BACKUP:-1" in wrapper
    assert "bash -s -- backup" in wrapper
    assert 'backup_archive="${backup_output##*$' in wrapper
    assert "test -f '$backup_archive.manifest.json'" in wrapper
    assert "RG_WEB_CORS_ORIGINS" in wrapper
    assert "RG_WEB_DISABLED_PROJECT_TYPES" in wrapper
    assert "REPORTGEN_DISABLED_PROJECT_TYPES" in wrapper
    assert "VITE_DISABLED_PROJECT_TYPES" in wrapper
    assert f"RG_WEB_DISABLED_PROJECT_TYPES:-{limited_release_panels}" in wrapper
    assert "scripts/check_production_panel_scope.py" in wrapper
    assert wrapper.index("scripts/check_production_panel_scope.py") < wrapper.index(
        "RUN_REMOTE_BACKUP"
    )
    assert "REQUIRE_ORIGIN_MAIN_REACHABILITY:-1" in wrapper
    assert 'git fetch --prune "$ORIGIN_REMOTE" main' in wrapper
    assert 'git merge-base --is-ancestor "$resolved_ref" "$ORIGIN_MAIN_REF"' in wrapper
    assert wrapper.index("git merge-base --is-ancestor") < wrapper.index("RUN_REMOTE_BACKUP")

    alerts = _read("scripts/iyun62_alerts.sh")
    assert "OPS_LOGIN_URL" in alerts
    assert "OPS_AUTH_USERNAME" in alerts
    assert "RG_WEB_MONITOR_USERNAME" in alerts
    assert "RG_WEB_MONITOR_PASSWORD" in alerts
    assert '"Authorization": f"Bearer {token}"' in alerts

    cloudflared_start = _read("scripts/iyun129_start_cloudflared.sh")
    cloudflared_watchdog = _read("scripts/iyun129_watchdog_cloudflared.sh")
    assert "--protocol http2" in cloudflared_start
    assert "cloudflared_tunnel_ha_connections" in cloudflared_start
    assert "cloudflared_tunnel_ha_connections" in cloudflared_watchdog


def test_lung_methylation_remains_draft_and_formally_blocked() -> None:
    panel = yaml.safe_load(_read("panels/lung_methylation/panel.yaml"))
    readiness = yaml.safe_load(
        _read("panels/lung_methylation/release_readiness.yaml")
    )

    assert panel["status"] == "draft"
    assert panel["templates"][0]["status"] == "draft"
    assert panel["golden_cases"][0]["synthetic"] is True
    assert panel["golden_cases"][0]["counts_as_production_evidence"] is False
    assert readiness["panel_id"] == "lung_methylation"
    assert readiness["release_status"] == "BLOCKED"
    assert readiness["production_eligible"] is False
    assert readiness["blocker_code"] == "formal_same_case_golden_pair_missing"
    assert readiness["promotion_evidence"]["same_case_verified"] is False
    assert (
        readiness["promotion_evidence"]["synthetic_golden"][
            "counts_as_production_evidence"
        ]
        is False
    )


def test_lung13_draft_is_built_but_not_clinically_promoted() -> None:
    readiness = yaml.safe_load(
        _read("config/panel_product_readiness/lung_13.yaml")
    )

    assert readiness["panel_id"] == "lung_13"
    assert readiness["release_status"] == "DRAFT_REVIEW_ONLY"
    assert readiness["draft_generation_eligible"] is True
    assert readiness["production_eligible"] is False
    assert readiness["draft_build_allowed"] is True
    assert readiness["aggregate_inventory"]["historical_final_docx_count"] == 246
    assert readiness["aggregate_inventory"]["supplied_matching_lung_13_excel_count"] == 0
    assert readiness["aggregate_inventory"]["contains_patient_data"] is False
    assert (ROOT / "panels/lung_13/panel.yaml").exists()


def test_lung62_series_has_distinct_drafts_with_shared_ngs_identity() -> None:
    lung62 = yaml.safe_load(
        _read("config/panel_product_readiness/lung_62.yaml")
    )
    lung62_pdl1 = yaml.safe_load(
        _read("config/panel_product_readiness/lung_62_pdl1.yaml")
    )

    assert lung62["production_eligible"] is False
    assert lung62_pdl1["production_eligible"] is False
    assert lung62["draft_build_allowed"] is True
    assert lung62_pdl1["draft_build_allowed"] is True
    assert lung62["aggregate_inventory"]["historical_final_docx_count"] == 33
    assert lung62_pdl1["aggregate_inventory"]["historical_final_docx_count"] == 55
    assert lung62["aggregate_inventory"]["supplied_matching_lung_62_excel_count"] == 0
    assert (
        lung62_pdl1["aggregate_inventory"][
            "supplied_matching_lung_62_pdl1_excel_count"
        ]
        == 0
    )
    assert (
        lung62_pdl1["promotion_evidence"]["pdl1_case_source_contract"]["clone_required"]
        is False
    )
    assert (ROOT / "panels/lung_62/panel.yaml").exists()
    assert (ROOT / "panels/lung_62_pdl1/panel.yaml").exists()


def test_production_scope_gate_rejects_methylation_override(tmp_path: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/check_production_panel_scope.py"),
        "--project-root",
        str(ROOT),
        "--target",
        "iyun129",
        "--web-disabled",
        "crc_301_msi,lung_13,lung_62,lung_62_pdl1,lung_588",
        "--core-disabled",
        "crc_301_msi,lung_methylation,"
        "lung_13,lung_62,lung_62_pdl1,lung_588",
        "--frontend-disabled",
        "crc_301_msi,lung_methylation,"
        "lung_13,lung_62,lung_62_pdl1,lung_588",
        "--output-json",
        str(tmp_path / "blocked.json"),
    ]
    blocked = subprocess.run(command, capture_output=True, text=True)
    assert blocked.returncode == 1
    payload = json.loads((tmp_path / "blocked.json").read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"
    assert any("missing from web disabled scope" in row for row in payload["issues"])

    web_scope = "crc_301_msi,lung_13,lung_62,lung_62_pdl1,lung_588"
    command[command.index(web_scope)] = (
        "crc_301_msi,lung_methylation,"
        "lung_13,lung_62,lung_62_pdl1,lung_588"
    )
    command[-1] = str(tmp_path / "closed.json")
    closed = subprocess.run(command, capture_output=True, text=True)
    assert closed.returncode == 0, closed.stdout + closed.stderr
    payload = json.loads((tmp_path / "closed.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_iyun129_switch_enables_only_promoted_or_controlled_pilot_panels() -> None:
    release = _read("scripts/iyun129_release.sh")
    limited_release_panels = "crc_301_msi,lung_methylation"

    assert f"RG_WEB_DISABLED_PROJECT_TYPES:-{limited_release_panels}" in release
    assert "VITE_DISABLED_PROJECT_TYPES" in release
    assert "check_production_scope" in release
    assert release.index("check_production_scope") < release.index(
        'resolved_target="$(resolve_remote "$TARGET")"'
    )
    assert "lung_329_pdl1" not in limited_release_panels
    assert "lung_588_pdl1" not in limited_release_panels
    assert (
        'REPORTGEN_DISABLED_PROJECT_TYPES="${REPORTGEN_DISABLED_PROJECT_TYPES:-'
        '$RG_WEB_DISABLED_PROJECT_TYPES}"'
    ) in release


def test_iyun129_switch_rejects_blocked_panel_scope_before_ssh() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun129_release.sh"), "switch", "0123456"],
        cwd=ROOT,
        env={
            **os.environ,
            "RG_WEB_DISABLED_PROJECT_TYPES": (
                "crc_301_msi,lung_13,lung_62,lung_62_pdl1,lung_588"
            ),
            "REPORTGEN_DISABLED_PROJECT_TYPES": (
                "crc_301_msi,lung_methylation,"
                "lung_13,lung_62,lung_62_pdl1,lung_588"
            ),
            "VITE_DISABLED_PROJECT_TYPES": (
                "crc_301_msi,lung_methylation,"
                "lung_13,lung_62,lung_62_pdl1,lung_588"
            ),
        },
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert "missing from web disabled scope" in result.stdout
    assert "ssh:" not in result.stderr.lower()


def test_iyun129_wrapper_rejects_commit_not_reachable_from_origin_main(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("config", "user.name", "Synthetic Release Test")
    git("config", "user.email", "release-test@example.invalid")
    (repo / "scripts").mkdir()
    (repo / "panels/lung_methylation").mkdir(parents=True)
    (repo / "scripts/iyun62_deploy_clean.sh").write_text(
        "#!/usr/bin/env bash\nexit 99\n",
        encoding="utf-8",
    )
    (repo / "scripts/check_production_panel_scope.py").write_text(
        _read("scripts/check_production_panel_scope.py"),
        encoding="utf-8",
    )
    (repo / "panels/lung_methylation/release_readiness.yaml").write_text(
        _read("panels/lung_methylation/release_readiness.yaml"),
        encoding="utf-8",
    )
    git(
        "add",
        "scripts/iyun62_deploy_clean.sh",
        "scripts/check_production_panel_scope.py",
        "panels/lung_methylation/release_readiness.yaml",
    )
    git("commit", "-m", "synthetic main")
    git("branch", "-M", "main")
    git("remote", "add", "origin", str(origin))
    git("push", "-u", "origin", "main")
    origin_main = git("rev-parse", "HEAD")

    git("switch", "-c", "candidate")
    (repo / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    git("add", "candidate.txt")
    git("commit", "-m", "unmerged candidate")
    candidate = git("rev-parse", "HEAD")

    common_env = {
        **os.environ,
        "RUN_REMOTE_BACKUP": "0",
    }
    blocked = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun129_deploy_clean.sh")],
        cwd=repo,
        env={**common_env, "DEPLOY_REF": candidate},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert blocked.returncode != 0
    assert "not reachable from origin/main" in blocked.stderr

    reachable = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun129_deploy_clean.sh")],
        cwd=repo,
        env={**common_env, "DEPLOY_REF": origin_main},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert reachable.returncode != 0
    assert "not reachable from origin/main" not in reachable.stderr
    assert "Historical golden manifest is missing" in reachable.stderr


def test_runtime_control_is_configured_and_failure_safe() -> None:
    deploy = _read("scripts/iyun62_deploy_clean.sh")
    start = _read("scripts/iyun62_start_reportgen.sh")
    watchdog = _read("scripts/iyun62_watchdog.sh")
    release = _read("scripts/iyun129_release.sh")
    iyun129_deploy = _read("scripts/iyun129_deploy_clean.sh")

    assert "deployment.env.next" in deploy
    assert "resolved_ref" in deploy
    assert "Verify release identity" in deploy
    assert "wait_public_health" in deploy
    assert "PUBLIC_HEALTH_RETRIES" in deploy
    assert "PUBLIC_HEALTH_RETRY_INTERVAL_SECONDS" in deploy
    assert 'HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-180}"' in deploy
    assert "printf 'HEALTH_TIMEOUT_SECONDS=%q\\n'" in deploy
    assert 'HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-180}"' in start
    assert 'export HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-180}"' in iyun129_deploy
    assert deploy.index("Restart Cloudflare connector") < deploy.rindex("wait_public_health")
    assert 'DEPLOYMENT_ENV="${DEPLOYMENT_ENV:-$RUNTIME_DIR/deployment.env}"' in start
    assert start.index('if start_release "$RELEASE_DIR"; then') < start.index(
        'write_current_release "$RELEASE_DIR"'
    )
    assert "Attempting automatic rollback" in start
    assert 'process_state" = "Z"' in start
    assert '[[ "$process_cmdline" == *uvicorn* ]]' in start
    assert 'HEALTH_STABLE_CHECKS="${HEALTH_STABLE_CHECKS:-2}"' in start
    assert 'previous_release="$(validate_release "$previous_release")"' in start
    assert 'SWITCH_LOCK_FILE="${SWITCH_LOCK_FILE:-$RUNTIME_DIR/run/' in start
    assert '"$FLOCK_BIN" -x 9' in start
    assert "9>&- &" in start
    assert '"$FLOCK_BIN" -n -x 9' in watchdog
    assert "watchdog skip deployment switch lock held" in watchdog
    assert "REPORTGEN_SWITCH_LOCK_HELD=1" in watchdog
    assert "os.kill(pid, signal.SIGKILL)" in start
    assert "uvicorn processes did not terminate" in start
    assert start.count('. "$DEPLOYMENT_ENV"') >= 2
    assert "REPORTGEN_FAST_TOC" in start
    assert "must be disabled for production report generation" in start
    assert "REPORTGEN_REQUIRE_RENDER_STACK=1" in deploy
    assert "Missing required report-render command" in start
    assert "import uno" in start
    assert "renderer_fingerprint.json" in start
    assert "zh_font_match_sha256" in start
    assert "font_substitution_fingerprint" in start
    assert "require_available=True" in start
    assert "REPORTGEN_LO_LOCK_FILE" in deploy
    assert start.index("must be disabled for production report generation") < start.index(
        "stop_existing\nif start_release"
    )
    assert "RG_WEB_RUNTIME_INSTANCE_LOCK_ENABLED=1" in deploy
    assert "RG_WEB_DISABLED_PROJECT_TYPES" in deploy
    assert "REPORTGEN_DISABLED_PROJECT_TYPES" in deploy
    assert "VITE_DISABLED_PROJECT_TYPES" in deploy
    assert 'RG_WEB_DISABLED_PROJECT_TYPES=""' in deploy
    assert 'REPORTGEN_DISABLED_PROJECT_TYPES=""' in deploy
    assert 'VITE_DISABLED_PROJECT_TYPES=""' in deploy
    assert deploy.index('REPORTGEN_DISABLED_PROJECT_TYPES=""') < deploy.index(
        "make release-check"
    )
    assert "backend/app/api/health.py" in deploy
    assert "TUNNEL_METRICS_URL" in deploy
    assert "check_signature_registry.py" in deploy
    assert 'rsync -az "$SIGNATURE_ASSET_DIR/"' in deploy
    release_check = _read("scripts/release_check.sh")
    assert "check_historical_golden_release.py" in release_check
    assert "REQUIRE_HISTORICAL_GOLDEN" in release_check
    assert 'MANAGE_TUNNEL="${MANAGE_TUNNEL:-1}"' in watchdog
    assert 'log "tunnel ok connector_connections=$connections external_manager"' in watchdog
    assert 'log "tunnel fail connector_connections=${connections:-0} external_manager"' in watchdog
    assert "/api/v1/healthz" in start
    assert "LEGACY_LOCAL_HEALTH_URL" in start
    assert 'if [ ! -f "$expected_cwd/backend/app/api/health.py" ]' in start
    assert "LEGACY_LOCAL_HEALTH_URL" in watchdog
    assert 'release_health_url "$release"' in watchdog
    assert "/api/v1/healthz" in release
    assert "LEGACY_LOCAL_HEALTH_URL" in release
    assert 'if [ ! -f "$current/backend/app/api/health.py" ]' in release
    assert "status|switch|rollback" in release
    assert "Expected exactly one release" in release

    web_smoke = _read("scripts/web_smoke.py")
    assert 'request_headers.setdefault("Authorization", f"Bearer {ACCESS_TOKEN}")' in web_smoke
    assert '"/api/v1/healthz"' in web_smoke
    assert "task stats must require authentication" in web_smoke

    backup = _read("scripts/iyun62_backup.sh")
    restore = _read("scripts/iyun62_restore_drill.sh")
    maintenance_installer = _read("scripts/iyun62_install_maintenance.sh")
    alerts_installer = _read("scripts/iyun62_install_alerts.sh")
    iyun129_maintenance = _read("scripts/iyun129_install_maintenance.sh")
    iyun129_alerts = _read("scripts/iyun129_install_alerts.sh")
    assert '"patient_info.yaml"' in backup
    assert "reference_reports patient_info.yaml" in backup
    assert '"patient_info.yaml"' in restore
    assert "RESTORE_DRILL_SCHEDULE" in maintenance_installer
    assert "restore_drill.sh run" in maintenance_installer
    assert "APP_ROOT=$APP_ROOT" in alerts_installer
    assert "PORT=$PORT" in alerts_installer
    assert "OPS_URL=$CRON_OPS_URL" in alerts_installer
    assert "SSH_HOST:-iyun129" in iyun129_maintenance
    assert "reportgen-web-storage" in iyun129_maintenance
    assert "SSH_HOST:-iyun129" in iyun129_alerts
    assert "PORT:-18082" in iyun129_alerts


def test_deploy_preflight_clears_runtime_panel_guards(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    fake_bin = tmp_path / "fake-bin"
    capture = tmp_path / "preflight.env"
    (repo / "frontend").mkdir(parents=True)
    (repo / "scripts").mkdir()
    fake_bin.mkdir()
    (repo / "frontend/package.json").write_text("{}\n", encoding="utf-8")
    for name in ("iyun62_start_reportgen.sh", "iyun62_watchdog.sh"):
        (repo / "scripts" / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_make = fake_bin / "make"
    fake_make.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s|%s\\n' "
        '"${RG_WEB_DISABLED_PROJECT_TYPES-<unset>}" '
        '"${REPORTGEN_DISABLED_PROJECT_TYPES-<unset>}" '
        '"${VITE_DISABLED_PROJECT_TYPES-<unset>}" > "$CAPTURE_FILE"\n'
        "exit 42\n",
        encoding="utf-8",
    )
    fake_make.chmod(0o755)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Synthetic Release Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "release-test@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "synthetic release"], cwd=repo, check=True)

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun62_deploy_clean.sh")],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "CAPTURE_FILE": str(capture),
            "RG_WEB_DISABLED_PROJECT_TYPES": "crc_301_msi",
            "REPORTGEN_DISABLED_PROJECT_TYPES": "crc_301_msi",
            "VITE_DISABLED_PROJECT_TYPES": "crc_301_msi",
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 42
    assert capture.read_text(encoding="utf-8") == "||\n"


@pytest.mark.parametrize(
    ("has_health_module", "expected_url"),
    [
        (False, "http://legacy.invalid/api/v1/tasks/stats"),
        (True, "http://candidate.invalid/api/v1/healthz"),
    ],
)
def test_release_status_uses_endpoint_supported_by_current_release(
    tmp_path: Path,
    has_health_module: bool,
    expected_url: str,
) -> None:
    runtime = tmp_path / "runtime"
    release = tmp_path / "releases" / "1111111"
    fake_bin = tmp_path / "fake-bin"
    runtime.mkdir()
    release.mkdir(parents=True)
    fake_bin.mkdir()
    (runtime / "current_release").write_text(str(release) + "\n", encoding="utf-8")
    (runtime / "reportgen-web.pid").write_text("12345\n", encoding="utf-8")
    (release / "REVISION").write_text("1" * 40 + "\n", encoding="utf-8")
    if has_health_module:
        health_module = release / "backend/app/api/health.py"
        health_module.parent.mkdir(parents=True)
        health_module.write_text("# synthetic health module\n", encoding="utf-8")

    fake_ssh = fake_bin / "ssh"
    fake_ssh.write_text(
        '#!/usr/bin/env bash\nshift\nexec "$@"\n',
        encoding="utf-8",
    )
    fake_readlink = fake_bin / "readlink"
    fake_readlink.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$EXPECTED_CWD\"\n",
        encoding="utf-8",
    )
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            url=""
            for arg in "$@"; do
                case "$arg" in
                    http://*|https://*) url="$arg" ;;
                esac
            done
            printf '%s\n' "$url" >> "$CURL_LOG"
            printf '200'
            """
        ),
        encoding="utf-8",
    )
    for executable in (fake_ssh, fake_readlink, fake_curl):
        executable.chmod(0o755)

    curl_log = tmp_path / "curl.log"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun129_release.sh"), "status"],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SSH_HOST": "synthetic-host",
            "RUNTIME_DIR": str(runtime),
            "LOCAL_HEALTH_URL": "http://candidate.invalid/api/v1/healthz",
            "LEGACY_LOCAL_HEALTH_URL": "http://legacy.invalid/api/v1/tasks/stats",
            "EXPECTED_CWD": str(release),
            "CURL_LOG": str(curl_log),
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert curl_log.read_text(encoding="utf-8").splitlines() == [expected_url]
    assert "health=HTTP 200" in result.stdout


def test_runtime_start_rejects_fast_toc_before_process_stop(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    runtime = tmp_path / "runtime"
    storage = tmp_path / "storage"
    venv = tmp_path / "venv"
    release = releases / "1111111"
    for path in (release, runtime, storage, venv / "bin"):
        path.mkdir(parents=True, exist_ok=True)
    (release / "REVISION").write_text("1" * 40 + "\n", encoding="utf-8")
    (runtime / ".env.prod").write_text(
        "RG_WEB_SECRET_KEY=synthetic-test-only\nREPORTGEN_FAST_TOC=1\n",
        encoding="utf-8",
    )
    (venv / "bin" / "python").symlink_to(sys.executable)
    uvicorn = venv / "bin" / "uvicorn"
    uvicorn.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    uvicorn.chmod(0o755)

    process = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun62_start_reportgen.sh")],
        env={
            **os.environ,
            "RELEASES_DIR": str(releases),
            "RUNTIME_DIR": str(runtime),
            "STORAGE_DIR": str(storage),
            "VENV_DIR": str(venv),
            "RELEASE_DIR": str(release),
            "FLOCK_BIN": "true",
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert process.returncode != 0
    assert "REPORTGEN_FAST_TOC must be disabled" in process.stderr
    assert not (runtime / "reportgen-web.pid").exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="flock test is Linux-only")
def test_watchdog_skips_during_release_switch(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    lock_file = runtime / "run" / "reportgen-web.switch.lock"
    watchdog_log = runtime / "logs" / "watchdog.log"
    lock_file.parent.mkdir(parents=True)

    holder = subprocess.Popen(
        [
            "bash",
            "-c",
            'exec 9> "$1"; flock -x 9; printf ready > "$2"; sleep 10',
            "synthetic-lock-holder",
            str(lock_file),
            str(tmp_path / "ready"),
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()

        result = subprocess.run(
            ["bash", str(ROOT / "scripts/iyun62_watchdog.sh")],
            env={
                **os.environ,
                "RUNTIME_DIR": str(runtime),
                "SWITCH_LOCK_FILE": str(lock_file),
                "DEPLOYMENT_ENV": str(tmp_path / "missing-deployment.env"),
            },
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0, result.stderr
        assert "watchdog skip deployment switch lock held" in watchdog_log.read_text(
            encoding="utf-8"
        )
        assert "watchdog begin" not in watchdog_log.read_text(encoding="utf-8")
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_watchdog_fails_closed_without_switch_lock_command(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/iyun62_watchdog.sh")],
        env={
            **os.environ,
            "RUNTIME_DIR": str(runtime),
            "FLOCK_BIN": str(tmp_path / "missing-flock"),
            "DEPLOYMENT_ENV": str(tmp_path / "missing-deployment.env"),
        },
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert "watchdog fail missing switch-lock command=" in (
        runtime / "logs" / "watchdog.log"
    ).read_text(encoding="utf-8")


def test_release_cli_runs_all_required_regression_suites_by_default() -> None:
    cli = _read("reportgen/cli.py")
    option = cli.split('"--pytest-args"', 1)[1].split("show_default=True", 1)[0]

    assert "backend/tests/test_report_regression.py" in option
    assert "backend/tests/test_knowledge_governance.py" in option
    assert "backend/tests/test_style_baseline.py" in option


def test_github_qa_installs_linux_renderer_before_running_gate() -> None:
    workflow = _read(".github/workflows/reportgen-qa.yml")

    install_index = workflow.index("libreoffice-writer")
    version_index = workflow.index("soffice --version")
    gate_index = workflow.index("python -m reportgen.cli qa gate")
    assert install_index < version_index < gate_index
    assert "fonts-noto-cjk" in workflow
    assert "poppler-utils" in workflow
    assert "python3-uno" in workflow
    assert "pdfinfo -v" in workflow
    assert "pdftotext -v" in workflow
    assert "pdftoppm -v" in workflow
    assert "font_substitution_fingerprint" in workflow
    assert "--render all" in workflow
    assert "--render-required" in workflow
    assert "python -m pytest backend/tests -q" in workflow
    assert "npm run lint" in workflow
    assert "npm audit --audit-level=moderate" in workflow
    assert "npm run build" in workflow


def test_release_gate_uses_the_same_exact_ruff_pin_locally_and_in_ci() -> None:
    requirements = _read("requirements-qa.txt")
    workflow = _read(".github/workflows/reportgen-qa.yml")
    makefile = _read("Makefile")
    backend_project = _read("backend/pyproject.toml")
    gate = _read("reportgen/core/qa_gate.py")

    assert "ruff==0.15.8" in requirements
    assert "-r requirements-qa.txt" in workflow
    assert "pip install -r requirements-qa.txt" in makefile
    assert '"ruff==0.15.8"' in backend_project
    assert "QA_ENV_MISSING_DEPENDENCY" in gate
    assert '"qa_toolchain"' in gate


def test_restore_drill_requires_attested_archive_and_restores_sqlite(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    (staging / "meta").mkdir(parents=True)
    (staging / "db").mkdir()
    database = staging / "db" / "reportgen_web.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()
    (staging / "meta" / "manifest.pre.json").write_text(
        json.dumps({"created_at": "synthetic", "revision": "a" * 40}),
        encoding="utf-8",
    )

    backup_dir = tmp_path / "backups"
    runtime_dir = tmp_path / "runtime"
    backup_dir.mkdir()
    archive = backup_dir / "reportgen-web-backup-20260719_010101.tar.gz"
    subprocess.run(
        ["tar", "-czf", str(archive), "-C", str(staging), "meta", "db"],
        check=True,
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest}  {archive.name}\n",
        encoding="utf-8",
    )
    archive.with_suffix(archive.suffix + ".manifest.json").write_text(
        json.dumps(
            {
                "created_at": "synthetic",
                "revision": "a" * 40,
                "archive": {
                    "filename": archive.name,
                    "bytes": archive.stat().st_size,
                    "sha256": digest,
                },
            }
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "APP_ROOT": str(tmp_path),
        "RUNTIME_DIR": str(runtime_dir),
        "BACKUP_DIR": str(backup_dir),
    }
    script = ROOT / "scripts/iyun62_restore_drill.sh"
    passed = subprocess.run(
        ["bash", str(script), "--archive", str(archive)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert passed.returncode == 0, passed.stderr
    reports = list((runtime_dir / "logs").glob("restore-drill-*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["checks"]["sqlite"]["integrity_check"] == "ok"

    archive.with_suffix(archive.suffix + ".sha256").unlink()
    rejected = subprocess.run(
        ["bash", str(script), "--archive", str(archive)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "Checksum sidecar missing" in rejected.stderr


def test_report_group_checklist_covers_audit_followups() -> None:
    checklist = _read("docs/report_group_system_report_audit_checklist.md")

    assert "已跟踪源码/测试/fixture" in checklist
    assert (
        "BPI-KB-01 高风险 provisional 可无痕交付 | RG-F13–F14、RG-I03–I06、SYN-FANCA-01"
    ) in checklist
    assert "BPI-KB-02 测试/历史疑似真实样本号 | RG-A04–A05、RG-A07" in checklist
    assert "renderer_fingerprint" in checklist
    assert "与生产同款 Linux LibreOffice" in checklist
    assert "Mac LibreOffice 结果不得替代生产等价渲染" in checklist


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/iyun62_deploy_clean.sh",
        "scripts/iyun62_start_reportgen.sh",
        "scripts/iyun62_watchdog.sh",
        "scripts/iyun129_deploy_clean.sh",
        "scripts/iyun129_release.sh",
        "scripts/iyun129_start_cloudflared.sh",
        "scripts/iyun129_watchdog_cloudflared.sh",
        "scripts/iyun129_install_alerts.sh",
        "scripts/iyun129_install_maintenance.sh",
        "scripts/iyun62_alerts.sh",
        "scripts/iyun62_install_alerts.sh",
        "scripts/iyun62_install_maintenance.sh",
        "scripts/iyun62_restore_drill.sh",
    ],
)
def test_release_shell_scripts_parse(relative: str) -> None:
    subprocess.run(["bash", "-n", str(ROOT / relative)], check=True)


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/iyun62_start_reportgen.sh",
        "scripts/iyun62_watchdog.sh",
        "scripts/iyun62_alerts.sh",
    ],
)
def test_embedded_python_blocks_compile(relative: str) -> None:
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY", _read(relative), flags=re.DOTALL)
    assert blocks
    for block in blocks:
        compile(block, f"{relative}:embedded", "exec")


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="runtime switch uses Linux /proc")
def test_failed_release_restores_previous_release(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    runtime = tmp_path / "runtime"
    storage = tmp_path / "storage"
    venv = tmp_path / "venv"
    fake_bin = tmp_path / "fake-bin"
    for path in (releases, runtime, storage, venv / "bin", fake_bin):
        path.mkdir(parents=True, exist_ok=True)

    good = releases / "1111111"
    bad = releases / "2222222"
    good.mkdir()
    bad.mkdir()
    (good / "REVISION").write_text("1" * 40 + "\n", encoding="utf-8")
    (bad / "REVISION").write_text("2" * 40 + "\n", encoding="utf-8")
    (bad / "FAIL_START").write_text("1\n", encoding="utf-8")
    (runtime / ".env.prod").write_text("RG_WEB_SECRET_KEY=synthetic-test-only\n", encoding="utf-8")

    (venv / "bin" / "python").symlink_to(sys.executable)
    fake_uvicorn = venv / "bin" / "uvicorn"
    fake_uvicorn.write_text(
        textwrap.dedent("""\
            import pathlib
            import time

            if (pathlib.Path.cwd() / "FAIL_START").exists():
                raise SystemExit(3)
            while True:
                time.sleep(1)
            """),
        encoding="utf-8",
    )
    fake_uvicorn.chmod(0o755)
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("#!/usr/bin/env bash\nprintf '200'\n", encoding="utf-8")
    fake_curl.chmod(0o755)

    port = str(41000 + os.getpid() % 1000)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "RELEASES_DIR": str(releases),
        "RUNTIME_DIR": str(runtime),
        "STORAGE_DIR": str(storage),
        "VENV_DIR": str(venv),
        "PORT": port,
        # Two consecutive health/cwd observations are required. Leave enough
        # time for the synthetic Python process to exec on a loaded CI runner.
        "HEALTH_TIMEOUT_SECONDS": "5",
        "REPORTGEN_REQUIRE_RENDER_STACK": "0",
    }
    script = ROOT / "scripts/iyun62_start_reportgen.sh"

    try:
        first = subprocess.run(
            ["bash", str(script)],
            env={**env, "RELEASE_DIR": str(good)},
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert first.returncode == 0, first.stderr
        assert (runtime / "current_release").read_text(encoding="utf-8").strip() == str(good)

        failed = subprocess.run(
            ["bash", str(script)],
            env={**env, "RELEASE_DIR": str(bad)},
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert failed.returncode != 0
        assert "Attempting automatic rollback" in failed.stderr
        assert (runtime / "current_release").read_text(encoding="utf-8").strip() == str(good)
        pid = int((runtime / "reportgen-web.pid").read_text(encoding="utf-8"))
        assert Path(f"/proc/{pid}/cwd").resolve() == good
        assert not Path(f"/proc/{pid}/fd/9").exists()
    finally:
        pid_file = runtime / "reportgen-web.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
