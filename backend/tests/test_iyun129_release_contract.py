from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import textwrap
import time
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
    assert "RG_WEB_CORS_ORIGINS" in wrapper
    assert "REQUIRE_ORIGIN_MAIN_REACHABILITY:-1" in wrapper
    assert 'git fetch --prune "$ORIGIN_REMOTE" main' in wrapper
    assert 'git merge-base --is-ancestor "$resolved_ref" "$ORIGIN_MAIN_REF"' in wrapper
    assert wrapper.index("git merge-base --is-ancestor") < wrapper.index(
        "RUN_REMOTE_BACKUP"
    )

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
    (repo / "scripts/iyun62_deploy_clean.sh").write_text(
        "#!/usr/bin/env bash\nexit 99\n",
        encoding="utf-8",
    )
    git("add", "scripts/iyun62_deploy_clean.sh")
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

    assert "deployment.env.next" in deploy
    assert "resolved_ref" in deploy
    assert "Verify release identity" in deploy
    assert "wait_public_health" in deploy
    assert "PUBLIC_HEALTH_RETRIES" in deploy
    assert "PUBLIC_HEALTH_RETRY_INTERVAL_SECONDS" in deploy
    assert deploy.index("Restart Cloudflare connector") < deploy.rindex(
        "wait_public_health"
    )
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
    assert start.index(
        "must be disabled for production report generation"
    ) < start.index("stop_existing\nif start_release")
    assert "RG_WEB_RUNTIME_INSTANCE_LOCK_ENABLED=1" in deploy
    assert "backend/app/api/health.py" in deploy
    assert "TUNNEL_METRICS_URL" in deploy
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
    assert '"patient_info.yaml"' in backup
    assert "reference_reports patient_info.yaml" in backup
    assert '"patient_info.yaml"' in restore


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
        "#!/usr/bin/env bash\nshift\nexec \"$@\"\n",
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
        assert not Path(f"/proc/{pid}/fd/9").exists()
    finally:
        pid_file = runtime / "reportgen-web.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
