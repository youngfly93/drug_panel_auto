from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_web_smoke_defaults_libreoffice_tmpdir_to_native_temp_root() -> None:
    script = (ROOT / "scripts" / "web_smoke.sh").read_text(encoding="utf-8")

    assert 'SYSTEM_TMP_ROOT="${TMPDIR:-/tmp}"' in script
    assert (
        'TMP_ROOT="${WEB_SMOKE_TMPDIR:-${SYSTEM_TMP_ROOT%/}/'
        'reportgen_web_smoke_tmp}"'
    ) in script
    assert '${ROOT}/tmp/web_smoke_tmp' not in script
