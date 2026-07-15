from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

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

    alerts = _read("scripts/iyun62_alerts.sh")
    assert "OPS_LOGIN_URL" in alerts
    assert "OPS_AUTH_USERNAME" in alerts
    assert '"Authorization": f"Bearer {token}"' in alerts

    cloudflared_start = _read("scripts/iyun129_start_cloudflared.sh")
    cloudflared_watchdog = _read("scripts/iyun129_watchdog_cloudflared.sh")
    assert "--protocol http2" in cloudflared_start
    assert "cloudflared_tunnel_ha_connections" in cloudflared_start
    assert "cloudflared_tunnel_ha_connections" in cloudflared_watchdog


def test_runtime_control_is_configured_and_failure_safe() -> None:
    deploy = _read("scripts/iyun62_deploy_clean.sh")
    start = _read("scripts/iyun62_start_reportgen.sh")
    watchdog = _read("scripts/iyun62_watchdog.sh")
    release = _read("scripts/iyun129_release.sh")

    assert "deployment.env.next" in deploy
    assert "resolved_ref" in deploy
    assert "Verify release identity" in deploy
    assert 'DEPLOYMENT_ENV="${DEPLOYMENT_ENV:-$RUNTIME_DIR/deployment.env}"' in start
    assert start.index('if start_release "$RELEASE_DIR"; then') < start.index(
        'write_current_release "$RELEASE_DIR"'
    )
    assert "Attempting automatic rollback" in start
    assert 'process_state" = "Z"' in start
    assert '[[ "$process_cmdline" == *uvicorn* ]]' in start
    assert 'HEALTH_STABLE_CHECKS="${HEALTH_STABLE_CHECKS:-2}"' in start
    assert 'previous_release="$(validate_release "$previous_release")"' in start
    assert "os.kill(pid, signal.SIGKILL)" in start
    assert "REPORTGEN_FAST_TOC" in start
    assert "must be disabled for production report generation" in start
    assert start.index(
        "must be disabled for production report generation"
    ) < start.index("stop_existing\nif start_release")
    assert "RG_WEB_RUNTIME_INSTANCE_LOCK_ENABLED=1" in deploy
    assert "check_signature_registry.py" in deploy
    assert 'rsync -az "$SIGNATURE_ASSET_DIR/"' in deploy
    release_check = _read("scripts/release_check.sh")
    assert "check_historical_golden_release.py" in release_check
    assert "REQUIRE_HISTORICAL_GOLDEN" in release_check
    assert 'MANAGE_TUNNEL="${MANAGE_TUNNEL:-1}"' in watchdog
    assert (
        'log "tunnel ok connector_connections=$connections external_manager"'
        in watchdog
    )
    assert (
        'log "tunnel fail connector_connections=${connections:-0} external_manager"'
        in watchdog
    )
    assert "/api/v1/healthz" in start
    assert "/api/v1/tasks/stats" not in start
    assert "status|switch|rollback" in release
    assert "Expected exactly one release" in release

    backup = _read("scripts/iyun62_backup.sh")
    restore = _read("scripts/iyun62_restore_drill.sh")
    assert '"patient_info.yaml"' in backup
    assert "reference_reports patient_info.yaml" in backup
    assert '"patient_info.yaml"' in restore


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
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert process.returncode != 0
    assert "REPORTGEN_FAST_TOC must be disabled" in process.stderr
    assert not (runtime / "reportgen-web.pid").exists()


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
    assert "pdfinfo -v" in workflow
    assert "pdftotext -v" in workflow


def test_report_group_checklist_covers_audit_followups() -> None:
    checklist = _read("docs/report_group_system_report_audit_checklist.md")

    assert "已跟踪源码/测试/fixture" in checklist
    assert (
        "BPI-KB-01 高风险 provisional 可无痕交付 | "
        "RG-F13–F14、RG-I03–I06、SYN-FANCA-01"
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
        "scripts/iyun62_alerts.sh",
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


@pytest.mark.skipif(
    not Path("/proc").is_dir(), reason="runtime switch uses Linux /proc"
)
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
    (runtime / ".env.prod").write_text(
        "RG_WEB_SECRET_KEY=synthetic-test-only\n", encoding="utf-8"
    )

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
        "HEALTH_TIMEOUT_SECONDS": "2",
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
        assert (runtime / "current_release").read_text(encoding="utf-8").strip() == str(
            good
        )

        failed = subprocess.run(
            ["bash", str(script)],
            env={**env, "RELEASE_DIR": str(bad)},
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert failed.returncode != 0
        assert "Attempting automatic rollback" in failed.stderr
        assert (runtime / "current_release").read_text(encoding="utf-8").strip() == str(
            good
        )
        pid = int((runtime / "reportgen-web.pid").read_text(encoding="utf-8"))
        assert Path(f"/proc/{pid}/cwd").resolve() == good
    finally:
        pid_file = runtime / "reportgen-web.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
