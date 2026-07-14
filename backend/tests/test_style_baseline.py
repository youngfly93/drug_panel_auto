# ruff: noqa: E402
"""金标样式基线回归测试。

把 crc_358 / crc_301 的**当前正确输出**冻结为基线（backend/tests/baselines/*.json）。
后处理层任何改动只要跑这两个测试，就能立刻发现是否把关键表的样式（链接色/下划线/
加粗）、第三部分 ❖ 颜色、签名区、参考文献覆盖弄坏了——把"改完怕崩、静默复发"变成
"改完有答案"。

这是慢测试（每个 panel 端到端生成约 2 分钟）。

更新基线（仅在确认输出变化是**有意**的之后）：
    REPORTGEN_UPDATE_BASELINE=1 pytest backend/tests/test_style_baseline.py -q
"""

import json
import os
import sys
from pathlib import Path

import pytest
from docx import Document
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.golden_case import GoldenCaseOptions, run_golden_case
from reportgen.core.signature_library import load_signature_entries
from reportgen.core.style_baseline import diff_baseline, extract_style_baseline

BASELINE_DIR = Path(__file__).parent / "baselines"


@pytest.mark.parametrize("panel", ["crc_358_msi", "crc_301_msi"])
def test_golden_style_baseline(panel: str, tmp_path, monkeypatch):
    # Signature images are runtime/PII assets and therefore must not be stored
    # in Git.  Build deterministic synthetic assets in an isolated external
    # storage root so this regression test has the same result on a clean CI
    # runner and on a workstation that happens to have production signatures.
    runtime_storage = tmp_path / "runtime-storage"
    monkeypatch.setenv("RG_WEB_STORAGE_ROOT", str(runtime_storage))
    runtime_storage = runtime_storage.resolve()
    for role, entries in load_signature_entries(ROOT / "config").items():
        color = (30, 120, 180) if role == "detector" else (120, 60, 160)
        for entry in entries:
            image_path = Path(entry.path)
            assert image_path.is_relative_to(runtime_storage), (
                f"test signature must resolve inside isolated storage: {image_path}"
            )
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (80, 30), color=color).save(image_path)

    result = run_golden_case(
        GoldenCaseOptions(
            panel=panel,
            config_dir=str(ROOT / "config"),
            output_root=str(tmp_path / "golden"),
            template_contract_mode="fail",
        )
    )
    assert result.get("ok"), result.get("errors")

    rendered_paragraphs = [
        (paragraph.text or "").strip()
        for paragraph in Document(result["output_file"]).paragraphs
    ]
    for required_tail_heading in (
        "本次检测质控结果",
        "高通量测序检测方法说明",
        "高通量测序局限性",
        "脉络医学检验简介",
    ):
        assert rendered_paragraphs.count(required_tail_heading) == 1

    actual = extract_style_baseline(result["output_file"])
    baseline_path = BASELINE_DIR / f"{panel}_style_baseline.json"

    if os.environ.get("REPORTGEN_UPDATE_BASELINE") == "1":
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        pytest.skip(f"已更新基线: {baseline_path.name}")

    assert baseline_path.exists(), (
        f"缺基线 {baseline_path.name}；先跑 "
        f"REPORTGEN_UPDATE_BASELINE=1 pytest {Path(__file__).name} 生成"
    )
    expected = json.loads(baseline_path.read_text(encoding="utf-8"))
    diffs = diff_baseline(expected, actual)
    assert not diffs, (
        f"[{panel}] 样式基线不一致——后处理改动可能弄坏了别处的格式。"
        f"若此变化是有意的，用 REPORTGEN_UPDATE_BASELINE=1 更新基线。\n差异:\n"
        + "\n".join(diffs[:40])
    )
