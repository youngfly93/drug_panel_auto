"""
CLI命令行接口

提供reportgen命令行工具。
"""

import json
import sys
from pathlib import Path

import click

from reportgen import __version__
from reportgen.utils.logger import get_logger


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config-dir",
    default="config",
    help="配置文件目录路径",
    show_default=True,
)
@click.option(
    "--log-file",
    default=None,
    help="日志文件路径（可选）",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="显示详细日志",
)
@click.pass_context
def cli(ctx, config_dir, log_file, verbose):
    """
    Excel到Docx自动化报告生成系统

    从Excel基因检测结果表生成标准化的docx医疗报告。
    """
    # 初始化上下文
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir
    ctx.obj["log_file"] = log_file
    ctx.obj["verbose"] = verbose

    # 设置日志级别
    log_level = "DEBUG" if verbose else "INFO"
    ctx.obj["log_level"] = log_level


@cli.command()
@click.option(
    "--excel",
    "-e",
    required=True,
    type=click.Path(exists=True),
    help="Excel结果文件路径",
)
@click.option(
    "--template",
    "-t",
    required=False,
    type=click.Path(exists=True),
    help="Docx模板文件路径（使用--auto-detect时可省略）",
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(),
    help="输出目录路径",
)
@click.option(
    "--filename",
    "-f",
    default=None,
    help="输出文件名（可选，默认自动生成）",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="严格模式：缺失关键字段时阻断生成（默认：只警告不阻断）",
)
@click.option(
    "--auto-detect",
    is_flag=True,
    default=False,
    help="自动检测项目类型并选择模板",
)
@click.option(
    "--template-contract",
    type=click.Choice(["none", "warn", "fail"]),
    default=None,
    help="模板契约校验模式（默认：auto-detect 时 fail，否则 warn）",
)
@click.option(
    "--project-type",
    default=None,
    help="显式指定项目类型（跳过自动检测，用于手动模板模式）",
)
@click.option(
    "--project-name",
    default=None,
    help="显式指定项目名称（覆盖 patient_info 全局默认值）",
)
@click.option(
    "--qa-visual-render",
    type=click.Choice(["none", "first", "all"]),
    default=None,
    help="生成后可选执行视觉QA渲染（默认读取 REPORTGEN_QA_VISUAL_RENDER 或 none）",
)
@click.option(
    "--qa-visual-render-required",
    is_flag=True,
    default=None,
    help="视觉QA失败时是否阻断生成QA状态",
)
@click.option("--qa-visual-render-dpi", type=int, default=None, help="视觉QA渲染DPI")
@click.option(
    "--qa-visual-render-timeout",
    type=int,
    default=None,
    help="视觉QA渲染超时时间（秒）",
)
@click.option(
    "--qa-visual-render-tmp-dir",
    default=None,
    type=click.Path(),
    help="视觉QA渲染临时目录",
)
@click.pass_context
def generate(
    ctx,
    excel,
    template,
    output,
    filename,
    strict,
    auto_detect,
    template_contract,
    project_type,
    project_name,
    qa_visual_render,
    qa_visual_render_required,
    qa_visual_render_dpi,
    qa_visual_render_timeout,
    qa_visual_render_tmp_dir,
):
    """
    生成单个报告

    示例:

        reportgen generate -e data/input/sample.xlsx \\
          -t templates/template.docx \\
          -o data/output/

        reportgen generate -e data/input/sample.xlsx -o data/output/ --auto-detect
    """
    config_dir = ctx.obj["config_dir"]
    log_file = ctx.obj["log_file"]
    verbose = ctx.obj["verbose"]

    # 初始化日志
    logger = get_logger(log_file=log_file, level=ctx.obj["log_level"])

    # 项目类型：显式 --project-type/--project-name 优先于 auto-detect
    prefetched_excel_data = None
    explicit_project_type = project_type       # 来自 --project-type
    explicit_project_name = project_name       # 来自 --project-name
    detected_project_type = explicit_project_type
    detected_project_name = explicit_project_name
    if auto_detect:
        from reportgen.core.excel_reader import ExcelReader
        from reportgen.core.project_detector import ProjectDetector

        click.echo(f"📊 Excel到Docx报告生成系统 v{__version__}")
        click.echo(f"📂 Excel文件: {excel}")
        click.echo("🔍 正在自动检测项目类型...")

        detector = ProjectDetector(
            config_dir=config_dir, log_file=log_file, log_level=ctx.obj["log_level"]
        )

        # 预读Excel（一次性读取，后续生成阶段复用，避免重复IO）
        excel_reader = ExcelReader(
            config_dir=config_dir, log_file=log_file, log_level=ctx.obj["log_level"]
        )
        try:
            prefetched_excel_data = excel_reader.read(excel, include_tables=True)
        except Exception as e:
            logger.warning(
                "自动检测阶段读取Excel失败，回退为仅文件名识别", error=str(e)
            )
            prefetched_excel_data = None

        detection_result = detector.detect(excel, excel_data=prefetched_excel_data)

        if detection_result["detected"]:
            detected_template = detection_result["template"]
            # 显式参数优先于检测结果
            if not detected_project_type:
                detected_project_type = detection_result.get("project_type")
            if not detected_project_name:
                detected_project_name = detection_result.get("project_name")
            click.echo(f"✅ 检测到项目类型: {detection_result['project_name']}")
            click.echo(f"   置信度: {detection_result['confidence']:.0%}")

            if template:
                click.echo(f"📄 使用指定模板: {template}")
            elif detected_template and Path(detected_template).exists():
                template = detected_template
                click.echo(f"📄 使用推荐模板: {template}")
            else:
                click.echo("⚠️  推荐模板不存在，请手动指定模板", err=True)
                sys.exit(1)
        else:
            click.echo("⚠️  无法自动检测项目类型", err=True)
            if not template:
                click.echo("请使用 -t 参数指定模板文件", err=True)
                sys.exit(1)
            click.echo(f"📄 使用指定模板: {template}")

        click.echo(f"📁 输出目录: {output}")
        click.echo("")
    else:
        # 非自动检测模式，模板必须指定
        if not template:
            click.echo(
                "❌ 错误: 请指定模板文件 (-t) 或使用 --auto-detect 自动检测", err=True
            )
            sys.exit(1)

        # 即使非 auto-detect，也做轻量检测以获取 project_type/name
        # （仅用于 enhancer 分派和上下文覆盖，不改变模板选择）
        # 始终运行检测，然后让显式参数覆盖检测结果
        try:
            from reportgen.core.excel_reader import ExcelReader
            from reportgen.core.project_detector import ProjectDetector

            _reader = ExcelReader(
                config_dir=config_dir, log_level=ctx.obj["log_level"]
            )
            prefetched_excel_data = _reader.read(excel, include_tables=True)
            _detector = ProjectDetector(
                config_dir=config_dir, log_level=ctx.obj["log_level"]
            )
            _det = _detector.detect(excel, excel_data=prefetched_excel_data)
            if _det.get("detected"):
                if not detected_project_type:
                    detected_project_type = _det.get("project_type")
                if not detected_project_name:
                    detected_project_name = _det.get("project_name")
        except Exception:
            pass  # 检测失败不影响手动模式

        click.echo(f"📊 Excel到Docx报告生成系统 v{__version__}")
        click.echo(f"📂 Excel文件: {excel}")
        click.echo(f"📄 模板文件: {template}")
        click.echo(f"📁 输出目录: {output}")
        click.echo("")

    try:
        from reportgen.core.report_generator import ReportGenerator

        # 初始化生成器
        generator = ReportGenerator(
            config_dir=config_dir,
            log_file=log_file,
            log_level=ctx.obj["log_level"],
        )

        # 验证输入
        if verbose:
            click.echo("🔍 验证输入参数...")

        is_valid, errors = generator.validate_inputs(excel, template, output)
        if not is_valid:
            click.echo("❌ 输入验证失败:", err=True)
            for error in errors:
                click.echo(f"   - {error}", err=True)
            sys.exit(1)

        # 生成报告
        if strict:
            click.echo("⚙️  正在生成报告（严格模式）...")
        else:
            click.echo("⚙️  正在生成报告...")

        # 确定模板契约校验模式：用户指定 > auto-detect 默认 fail > 其他默认 warn
        contract_mode = template_contract
        if contract_mode is None:
            contract_mode = "fail" if auto_detect else "warn"

        result = generator.generate(
            excel_file=excel,
            template_file=template,
            output_dir=output,
            output_filename=filename,
            strict_mode=strict,
            excel_data=prefetched_excel_data,
            project_type=detected_project_type,
            project_name=detected_project_name,
            template_contract_mode=contract_mode,
            qa_visual_render=qa_visual_render,
            qa_visual_render_required=qa_visual_render_required,
            qa_visual_render_dpi=qa_visual_render_dpi,
            qa_visual_render_timeout_seconds=qa_visual_render_timeout,
            qa_visual_render_tmp_dir=qa_visual_render_tmp_dir,
        )

        if result["success"]:
            click.echo("✅ 报告生成成功!")
            click.echo(f"📄 输出文件: {result['output_file']}")
            if result.get("panel_package_validation"):
                panel_status = (
                    result["panel_package_validation"].get("status") or "UNKNOWN"
                )
                click.echo(f"🧬 Panel校验: {panel_status}")
            if result.get("field_provenance_file"):
                click.echo(f"🧾 字段来源: {result['field_provenance_file']}")
            if result.get("qa_report_file"):
                qa_status = result.get("qa_status") or "UNKNOWN"
                click.echo(f"🧪 QA报告: {result['qa_report_file']} ({qa_status})")
            click.echo(f"⏱️  耗时: {result['duration']:.2f}秒")

            # 显示警告
            if result["warnings"]:
                click.echo(f"\n⚠️  警告 ({len(result['warnings'])}个):")
                for warning in result["warnings"]:
                    click.echo(f"   - {warning}")

            sys.exit(0)
        else:
            click.echo("❌ 报告生成失败!", err=True)
            click.echo(f"⏱️  耗时: {result['duration']:.2f}秒", err=True)

            if result["errors"]:
                click.echo("\n错误详情:", err=True)
                for error in result["errors"]:
                    click.echo(f"   - {error}", err=True)

            sys.exit(1)

    except Exception as e:
        logger.error("命令执行失败", command="generate", error=str(e))
        click.echo(f"❌ 执行失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--inputs",
    multiple=True,
    default=("data/input",),
    show_default=True,
    help="输入目录/文件/glob（可重复指定，例如 --inputs data/input --inputs 2025.12.10）",
)
@click.option(
    "--name-contains",
    default=None,
    help="仅处理文件名包含该子串的Excel（不区分大小写）",
)
@click.option(
    "--template",
    default=None,
    type=click.Path(exists=True),
    help="强制指定模板（默认：自动识别项目类型选择模板）",
)
@click.option(
    "--output-root",
    default=None,
    type=click.Path(),
    help="输出根目录（默认：data/output/batch_validate_<timestamp>）",
)
@click.option("--max-files", type=int, default=None, help="最多处理多少个Excel（可选）")
@click.option(
    "--render",
    type=click.Choice(["none", "first", "all"]),
    default="none",
    show_default=True,
    help="将输出docx渲染为PNG页图（用于版式快速检查）",
)
@click.option("--render-dpi", type=int, default=120, show_default=True, help="渲染DPI")
@click.option(
    "--highlight",
    is_flag=True,
    default=False,
    help="生成高亮版docx（标注动态填充区域）",
)
@click.option(
    "--highlight-color", default="D9EAF7", show_default=True, help="高亮底色（HEX）"
)
@click.option(
    "--highlight-output-root",
    default=None,
    type=click.Path(),
    help="高亮版输出根目录（默认：output/doc/highlighted/<batch_dir>/）",
)
@click.option(
    "--emit-context/--no-emit-context",
    default=True,
    show_default=True,
    help="输出脱敏context.json",
)
@click.option(
    "--emit-meta/--no-emit-meta",
    default=True,
    show_default=True,
    help="输出meta.json（hash/参数/版本等）",
)
@click.option(
    "--artifacts-dir-mode",
    type=click.Choice(["separate", "alongside"]),
    default="separate",
    show_default=True,
    help="追溯产物（context/meta）放置方式",
)
@click.option(
    "--template-contract",
    type=click.Choice(["none", "warn", "fail"]),
    default="fail",
    show_default=True,
    help="模板契约：模板引用缺失变量时的处理策略",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="CRITICAL",
    show_default=True,
    help="reportgen内部日志级别（-v 会强制DEBUG）",
)
@click.option(
    "--report-file",
    default=None,
    type=click.Path(),
    help="将汇总JSON写到指定路径（可选）",
)
@click.option(
    "--show-paths",
    is_flag=True,
    default=False,
    help="打印完整输入/输出路径（默认关闭，避免泄露标识）",
)
@click.pass_context
def batch_validate(
    ctx,
    inputs,
    name_contains,
    template,
    output_root,
    max_files,
    render,
    render_dpi,
    highlight,
    highlight_color,
    highlight_output_root,
    emit_context,
    emit_meta,
    artifacts_dir_mode,
    template_contract,
    log_level,
    report_file,
    show_paths,
):
    """
    批量生成 + 校验（Excel -> DOCX）

    附加能力：
    - 模板契约校验（缺失变量/字段 fail/warn）
    - 追溯产物（脱敏context.json + meta.json）
    - 生成高亮版docx（便于定位模板动态区域）
    - 可选渲染PNG页图（快速人工验收版式）
    """
    from reportgen.core.batch_runner import (
        BatchValidateOptions,
        run_batch_generate_validate,
    )

    if ctx.obj.get("verbose"):
        log_level = "DEBUG"

    opts = BatchValidateOptions(
        inputs=list(inputs),
        name_contains=name_contains,
        template=template,
        config_dir=ctx.obj["config_dir"],
        output_root=output_root,
        max_files=max_files,
        render=render,
        render_dpi=int(render_dpi),
        highlight=bool(highlight),
        highlight_color=highlight_color,
        highlight_output_root=highlight_output_root,
        emit_context=bool(emit_context),
        emit_meta=bool(emit_meta),
        artifacts_dir_mode=artifacts_dir_mode,
        template_contract=template_contract,
        log_level=log_level,
        report_file=report_file,
        show_paths=bool(show_paths),
    )

    try:
        run = run_batch_generate_validate(opts, progress=click.echo)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(2)

    report_obj = run.report
    click.echo("\nSummary:")
    click.echo(f"  inputs: {report_obj.get('inputs_count')}")
    click.echo(f"  success: {report_obj.get('successes')}")
    click.echo(f"  failed: {report_obj.get('failures')}")
    click.echo(f"  report: {run.report_path}")
    click.echo(f"  output_root: {run.output_root}")

    sys.exit(0 if int(report_obj.get("failures") or 0) == 0 else 1)


@cli.group()
def panel():
    """Panel package management commands."""


@panel.command("validate")
@click.argument("panel_id", required=False)
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(),
    help="项目根目录，默认当前目录",
)
@click.option(
    "--panels-dir",
    default="panels",
    show_default=True,
    type=click.Path(),
    help="Panel Package目录",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="输出格式",
)
@click.option(
    "--fail-on",
    type=click.Choice(["error", "warn"]),
    default="error",
    show_default=True,
    help="CLI非零退出门槛",
)
def panel_validate(panel_id, project_root, panels_dir, output_format, fail_on):
    """Validate one Panel Package or the whole registry."""
    from reportgen.panels.validation import (
        validate_panel_package,
        validate_panel_registry,
    )

    if panel_id:
        report = validate_panel_package(
            panel_id,
            project_root=project_root,
            panels_dir=panels_dir,
        )
    else:
        report = validate_panel_registry(
            project_root=project_root,
            panels_dir=panels_dir,
        )

    payload = report.to_dict()
    if output_format == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Panel validation: {payload['status']}")
        click.echo(f"  scope: {payload['scope']}")
        click.echo(f"  panels: {', '.join(payload['panels_checked']) or 'none'}")
        summary = payload["summary"]
        click.echo(
            "  issues: "
            f"{summary['errors']} errors, {summary['warnings']} warnings"
        )
        for issue in payload["issues"]:
            click.echo(
                f"  - {issue['level']} {issue['code']}"
                f" [{issue.get('panel_id') or '-'}]: {issue['message']}"
            )
            if issue.get("path"):
                click.echo(f"    path: {issue['path']}")
            if issue.get("hint"):
                click.echo(f"    hint: {issue['hint']}")

    if report.errors or (fail_on == "warn" and report.warnings):
        sys.exit(1)
    sys.exit(0)


@cli.group()
def qa():
    """QA and golden-case regression commands."""


@qa.command("run")
@click.option(
    "--panel",
    default="crc_358_msi",
    show_default=True,
    help="要运行的 golden case Panel ID",
)
@click.option(
    "--output-root",
    default=None,
    type=click.Path(),
    help="golden case 输出目录（默认写入 tmp/golden_cases/）",
)
@click.option(
    "--template",
    "template_file",
    default=None,
    type=click.Path(exists=True),
    help="覆盖默认模板路径",
)
@click.option(
    "--template-contract",
    type=click.Choice(["none", "warn", "fail"]),
    default="fail",
    show_default=True,
    help="模板契约校验模式",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="ERROR",
    show_default=True,
    help="reportgen内部日志级别",
)
@click.option(
    "--render",
    type=click.Choice(["none", "first", "all"]),
    default="none",
    show_default=True,
    help="是否把 golden DOCX 渲染为 PNG 页面做视觉验收",
)
@click.option("--render-dpi", type=int, default=120, show_default=True, help="渲染DPI")
@click.option(
    "--render-timeout",
    type=int,
    default=120,
    show_default=True,
    help="单个渲染阶段超时时间（秒）",
)
@click.option(
    "--render-required/--render-optional",
    default=False,
    show_default=True,
    help="渲染失败是否使 golden case 失败",
)
@click.option(
    "--render-tmp-dir",
    default=None,
    type=click.Path(),
    help="渲染临时目录；也可使用 REPORTGEN_RENDER_TMPDIR",
)
@click.pass_context
def qa_run(
    ctx,
    panel,
    output_root,
    template_file,
    template_contract,
    log_level,
    render,
    render_dpi,
    render_timeout,
    render_required,
    render_tmp_dir,
):
    """运行单个 Panel 的端到端 golden case。"""
    from reportgen.core.golden_case import GoldenCaseOptions, run_golden_case

    if ctx.obj.get("verbose"):
        log_level = "DEBUG"

    opts = GoldenCaseOptions(
        panel=panel,
        config_dir=ctx.obj["config_dir"],
        template_file=template_file,
        output_root=output_root,
        log_level=log_level,
        template_contract_mode=template_contract,
        render=render,
        render_dpi=int(render_dpi),
        render_timeout_seconds=int(render_timeout),
        render_required=bool(render_required),
        render_tmp_dir=render_tmp_dir,
    )

    click.echo(f"🧪 Running golden case: {panel}")
    try:
        result = run_golden_case(opts)
    except Exception as e:
        click.echo(f"❌ Golden case failed before assertions: {e}", err=True)
        sys.exit(1)

    click.echo(f"  output: {result.get('output_file')}")
    click.echo(f"  qa: {result.get('qa_report_file')} ({result.get('qa_status')})")
    click.echo(f"  report: {result.get('golden_report_file')}")
    visual_render = result.get("visual_render") or {}
    if visual_render.get("requested") != "none":
        click.echo(
            "  render: "
            f"{visual_render.get('status')} "
            f"({len(visual_render.get('rendered_pages') or [])} page images)"
        )
        if visual_render.get("output_dir"):
            click.echo(f"  render_dir: {visual_render.get('output_dir')}")

    failed = [row for row in result.get("checks", []) if not row.get("passed")]
    if failed:
        click.echo("\nFailed checks:", err=True)
        for row in failed:
            click.echo(f"  - {row.get('name')}: {row.get('message')}", err=True)
            actual = row.get("actual")
            expected = row.get("expected")
            if expected is not None or actual is not None:
                click.echo(f"    expected={expected!r} actual={actual!r}", err=True)
        sys.exit(1)

    click.echo("✅ Golden case passed")
    sys.exit(0)


@qa.command("diff")
@click.option(
    "--reference",
    "reference_docx",
    required=True,
    type=click.Path(exists=True),
    help="基准/正确报告 DOCX",
)
@click.option(
    "--candidate",
    "candidate_docx",
    required=True,
    type=click.Path(exists=True),
    help="候选/新生成报告 DOCX",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="输出 report_diff.json 与 report_diff.md 的目录",
)
@click.option(
    "--reference-qa",
    default=None,
    type=click.Path(exists=True),
    help="基准报告 QA JSON；默认查找同名 .qa.json",
)
@click.option(
    "--candidate-qa",
    default=None,
    type=click.Path(exists=True),
    help="候选报告 QA JSON；默认查找同名 .qa.json",
)
@click.option(
    "--max-samples",
    default=30,
    show_default=True,
    type=int,
    help="每类差异最多保留的样本数",
)
@click.option(
    "--fail-on",
    type=click.Choice(["fail", "warn"]),
    default="fail",
    show_default=True,
    help="CLI 非零退出门槛",
)
def qa_diff(
    reference_docx,
    candidate_docx,
    output_dir,
    reference_qa,
    candidate_qa,
    max_samples,
    fail_on,
):
    """对比基准报告和候选报告，输出机器可读与人工可读 diff。"""
    from reportgen.core.report_diff import ReportDiffOptions, compare_reports

    result = compare_reports(
        ReportDiffOptions(
            reference_docx=reference_docx,
            candidate_docx=candidate_docx,
            output_dir=output_dir,
            reference_qa=reference_qa,
            candidate_qa=candidate_qa,
            max_samples=int(max_samples),
        )
    )

    summary = result.get("summary") or {}
    click.echo(f"🧾 Report diff status: {result.get('status')}")
    click.echo(
        "  failures: "
        f"{summary.get('failures', 0)}, warnings: {summary.get('warnings', 0)}, "
        f"text_similarity: {summary.get('text_similarity')}"
    )
    if result.get("json_file"):
        click.echo(f"  json: {result.get('json_file')}")
    if result.get("markdown_file"):
        click.echo(f"  markdown: {result.get('markdown_file')}")
    for issue in list(result.get("issues") or [])[: int(max_samples)]:
        click.echo(
            f"  - {str(issue.get('level')).upper()} "
            f"{issue.get('section')}/{issue.get('code')}: {issue.get('message')}"
        )

    status = result.get("status")
    if status == "FAIL" or (fail_on == "warn" and status == "WARN"):
        sys.exit(1)
    sys.exit(0)


@qa.command("legacy-snapshot")
@click.option(
    "--panel",
    required=True,
    help="历史报告所属 Panel ID，例如 crc_301_msi",
)
@click.option(
    "--source-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="按 panel 拆分后的历史 DOCX 目录",
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(),
    help="脱敏 reference snapshot 输出目录",
)
@click.option(
    "--sample-count",
    default=5,
    show_default=True,
    type=int,
    help="选择的代表样本数量",
)
@click.option(
    "--max-text-chars",
    default=12000,
    show_default=True,
    type=int,
    help="每份脱敏文本摘录最多保留字符数",
)
@click.option(
    "--include-source-paths",
    is_flag=True,
    default=False,
    help="调试用：在快照中保留原始路径/文件名。默认关闭，避免患者信息进入产物。",
)
def qa_legacy_snapshot(
    panel,
    source_dir,
    output_dir,
    sample_count,
    max_text_chars,
    include_source_paths,
):
    """从历史 DOCX 报告构建脱敏 reference snapshots。"""
    from reportgen.core.legacy_reference import (
        LegacySnapshotOptions,
        build_legacy_reference_snapshots,
    )

    result = build_legacy_reference_snapshots(
        LegacySnapshotOptions(
            panel=panel,
            source_dir=source_dir,
            output_dir=output_dir,
            sample_count=int(sample_count),
            include_source_paths=bool(include_source_paths),
            max_text_chars=int(max_text_chars),
        )
    )
    click.echo(f"🧾 Legacy snapshots: {result.get('status')}")
    click.echo(f"  source_docx_count: {result.get('source_docx_count')}")
    click.echo(f"  readable_docx_count: {result.get('readable_docx_count')}")
    click.echo(f"  read_error_count: {result.get('read_error_count')}")
    click.echo(f"  selected_count: {result.get('selected_count')}")
    click.echo(f"  manifest: {result.get('manifest_file')}")
    click.echo(f"  markdown: {result.get('markdown_file')}")


@qa.command("gate")
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(),
    help="项目根目录，默认当前目录",
)
@click.option(
    "--output-root",
    default=None,
    type=click.Path(),
    help="门禁产物输出目录（默认写入 tmp/qa_gate/）",
)
@click.option(
    "--panel",
    "panels",
    multiple=True,
    help="要运行的 golden panel，可重复或用逗号分隔；默认运行核心 panel",
)
@click.option(
    "--lint/--skip-lint",
    "run_lint",
    default=True,
    show_default=True,
    help="是否运行 ruff 检查",
)
@click.option(
    "--pytest/--skip-pytest",
    "run_pytest",
    default=True,
    show_default=True,
    help="是否运行 pytest 回归",
)
@click.option(
    "--golden/--skip-golden",
    "run_golden",
    default=True,
    show_default=True,
    help="是否运行 golden case",
)
@click.option(
    "--diff/--skip-diff",
    "run_diff",
    default=True,
    show_default=True,
    help="是否对重复 golden 结果执行结构 diff",
)
@click.option(
    "--current-output/--skip-current-output",
    "run_current_output",
    default=True,
    show_default=True,
    help="是否按 panel qa.yaml 校验当前生成 DOCX 输出",
)
@click.option(
    "--legacy-reference/--skip-legacy-reference",
    "run_legacy_reference",
    default=True,
    show_default=True,
    help="是否运行历史报告脱敏 reference snapshot 门禁",
)
@click.option(
    "--legacy-source-root",
    default=None,
    type=click.Path(file_okay=False),
    help="历史报告按 panel 拆分后的根目录；也可用 REPORTGEN_LEGACY_REPORTS_ROOT",
)
@click.option(
    "--legacy-panel",
    "legacy_panels",
    multiple=True,
    help="要运行历史 reference 的 panel，可重复或用逗号分隔；默认读取 panel qa.yaml 中启用项",
)
@click.option(
    "--legacy-sample-count",
    default=None,
    type=int,
    help="覆盖 qa.yaml 中每个 panel 抽取的历史 reference 样本数",
)
@click.option(
    "--legacy-reference-required/--legacy-reference-optional",
    "legacy_required",
    default=False,
    show_default=True,
    help="历史报告目录缺失时是否阻断门禁",
)
@click.option(
    "--pytest-args",
    default="backend/tests/test_report_regression.py -q",
    show_default=True,
    help="pytest 参数字符串",
)
@click.option(
    "--fail-on",
    type=click.Choice(["fail", "warn"]),
    default="warn",
    show_default=True,
    help="门禁非零退出门槛",
)
@click.option(
    "--render",
    type=click.Choice(["none", "first", "all"]),
    default="none",
    show_default=True,
    help="golden case 可选视觉渲染模式",
)
@click.option(
    "--render-required/--render-optional",
    default=False,
    show_default=True,
    help="视觉渲染失败是否阻断门禁",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="ERROR",
    show_default=True,
    help="reportgen内部日志级别",
)
def qa_gate(
    project_root,
    output_root,
    panels,
    run_lint,
    run_pytest,
    run_golden,
    run_diff,
    run_current_output,
    run_legacy_reference,
    legacy_source_root,
    legacy_panels,
    legacy_sample_count,
    legacy_required,
    pytest_args,
    fail_on,
    render,
    render_required,
    log_level,
):
    """运行 CI / 部署前质量门禁。"""
    import shlex

    from reportgen.core.qa_gate import (
        DEFAULT_GATE_PANELS,
        QualityGateOptions,
        run_quality_gate,
    )

    selected_panels = []
    for item in panels:
        selected_panels.extend(
            part.strip() for part in str(item).split(",") if part.strip()
        )
    if not selected_panels:
        selected_panels = list(DEFAULT_GATE_PANELS)

    selected_legacy_panels = []
    for item in legacy_panels:
        selected_legacy_panels.extend(
            part.strip() for part in str(item).split(",") if part.strip()
        )

    click.echo("🧱 Running reportgen QA gate")
    result = run_quality_gate(
        QualityGateOptions(
            project_root=project_root,
            output_root=output_root,
            panels=tuple(selected_panels),
            run_lint=bool(run_lint),
            run_pytest=bool(run_pytest),
            run_golden=bool(run_golden),
            run_diff=bool(run_diff),
            run_current_output=bool(run_current_output),
            run_legacy_reference=bool(run_legacy_reference),
            fail_on_warn=(fail_on == "warn"),
            pytest_args=tuple(shlex.split(pytest_args)),
            render=render,
            render_required=bool(render_required),
            log_level=log_level,
            legacy_source_root=legacy_source_root,
            legacy_panels=tuple(selected_legacy_panels),
            legacy_sample_count=(
                int(legacy_sample_count) if legacy_sample_count is not None else None
            ),
            legacy_required=bool(legacy_required),
        )
    )

    click.echo(f"  status: {result.get('status')}")
    click.echo(f"  report: {result.get('report_file')}")
    click.echo(f"  output_root: {result.get('output_root')}")
    for step in result.get("steps") or []:
        icon = {
            "PASS": "✅",
            "WARN": "⚠️",
            "FAIL": "❌",
            "SKIPPED": "⏭️",
        }.get(step.get("status"), "•")
        click.echo(
            f"  {icon} {step.get('name')}: {step.get('status')} "
            f"({step.get('duration_seconds')}s)"
        )
        if step.get("status") == "FAIL":
            if step.get("error"):
                click.echo(f"      error: {step.get('error')}", err=True)
            for issue in list(step.get("issues") or [])[:5]:
                click.echo(
                    f"      issue: {issue.get('code')} {issue.get('message')}",
                    err=True,
                )
            if step.get("log_file"):
                click.echo(f"      log: {step.get('log_file')}", err=True)

    sys.exit(0 if result.get("status") == "PASS" else 1)


@cli.command()
@click.option(
    "--template",
    required=True,
    type=click.Path(exists=True),
    help="模板docx（含Jinja2/docxtpl标记）",
)
@click.option(
    "--input",
    "input_docx",
    required=True,
    type=click.Path(exists=True),
    help="已生成的报告docx",
)
@click.option("--output", required=True, type=click.Path(), help="输出高亮版docx路径")
@click.option("--color", default="D9EAF7", show_default=True, help="高亮底色（HEX）")
@click.option(
    "--skip-empty/--no-skip-empty",
    default=True,
    show_default=True,
    help="跳过空白run（更干净）",
)
@click.option(
    "--render",
    type=click.Choice(["none", "first", "all"]),
    default="none",
    show_default=True,
    help="可选：渲染高亮版docx为PNG页图",
)
@click.option("--render-dpi", type=int, default=120, show_default=True, help="渲染DPI")
@click.option(
    "--render-output-dir", default=None, type=click.Path(), help="PNG输出目录（可选）"
)
def highlight(
    template,
    input_docx,
    output,
    color,
    skip_empty,
    render,
    render_dpi,
    render_output_dir,
):
    """对生成的报告docx进行高亮（标出动态填充区域）。"""
    from reportgen.utils.docx_highlighter import highlight_rendered_docx
    from reportgen.utils.docx_render import render_docx_to_pngs

    out_path = Path(output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = highlight_rendered_docx(
        template_path=str(template),
        input_docx_path=str(input_docx),
        output_docx_path=str(out_path),
        color=str(color),
        skip_empty=bool(skip_empty),
    )

    click.echo("Highlight summary:")
    click.echo(f"  output: {Path(summary.output_docx).name}")
    click.echo(f"  color: {summary.color}")
    click.echo(f"  highlighted_runs: {summary.highlighted_runs}")
    click.echo(f"  matched_tables: {summary.matched_tables}/{summary.tables_processed}")
    click.echo(f"  paragraphs_highlighted: {summary.paragraphs_highlighted}")

    if render != "none":
        pages_dir = (
            Path(render_output_dir).resolve()
            if render_output_dir
            else out_path.parent / "pages" / out_path.stem
        )
        pages_dir.mkdir(parents=True, exist_ok=True)
        first_page = 1 if render == "first" else None
        last_page = 1 if render == "first" else None
        render_docx_to_pngs(
            Path(out_path),
            output_dir=pages_dir,
            dpi=int(render_dpi),
            keep_pdf=False,
            first_page=first_page,
            last_page=last_page,
        )
        click.echo(f"Rendered pages dir: {pages_dir.resolve()}")


@cli.command()
@click.option(
    "--report",
    default=None,
    type=click.Path(exists=True),
    help="指定validation_report.json（可选）",
)
@click.option(
    "--batch-root",
    default="data/output",
    show_default=True,
    type=click.Path(),
    help="查找 batch_validate_* 的根目录",
)
@click.option(
    "--output-root",
    default="output/doc/highlighted",
    show_default=True,
    type=click.Path(),
    help="高亮输出根目录",
)
@click.option("--color", default="D9EAF7", show_default=True, help="高亮底色（HEX）")
@click.option(
    "--skip-empty/--no-skip-empty", default=True, show_default=True, help="跳过空白run"
)
@click.option("--only-ok", is_flag=True, default=False, help="仅处理 ok=true 的样本")
@click.option("--max-files", type=int, default=None, help="最多处理多少个样本（可选）")
@click.option(
    "--render",
    type=click.Choice(["none", "first", "all"]),
    default="none",
    show_default=True,
    help="可选：渲染高亮版docx为PNG页图",
)
@click.option("--render-dpi", type=int, default=120, show_default=True, help="渲染DPI")
@click.option("--show-paths", is_flag=True, default=False, help="打印完整输入/输出路径")
def batch_highlight_latest(
    report,
    batch_root,
    output_root,
    color,
    skip_empty,
    only_ok,
    max_files,
    render,
    render_dpi,
    show_paths,
):
    """对最新一次 batch_validate 输出进行批量高亮。"""
    from reportgen.core.batch_highlight import (
        BatchHighlightOptions,
        run_batch_highlight_latest,
    )

    opts = BatchHighlightOptions(
        report=report,
        batch_root=batch_root,
        output_root=output_root,
        color=color,
        skip_empty=bool(skip_empty),
        only_ok=bool(only_ok),
        max_files=max_files,
        render=render,
        render_dpi=int(render_dpi),
        show_paths=bool(show_paths),
    )

    run = run_batch_highlight_latest(opts, progress=click.echo)

    click.echo("\nSummary:")
    click.echo(f"  processed: {run.report.get('processed')}")
    click.echo(f"  skipped: {run.report.get('skipped')}")
    click.echo(f"  failed: {run.report.get('failed')}")
    click.echo(f"  output_root: {run.output_root}")

    sys.exit(0 if int(run.report.get("failed") or 0) == 0 else 1)


@cli.command("explain-doc")
@click.option(
    "--template",
    default="templates/aligned_template_with_cnv_fusion_hla_FIXED.docx",
    type=click.Path(exists=True),
    show_default=True,
    help="用于定位变量/表格落点的模板docx",
)
@click.option(
    "--output",
    default="output/doc/Excel到Docx自动化说明书_主线模板.docx",
    type=click.Path(),
    show_default=True,
    help="输出说明书docx路径（建议放在 gitignored 的 output/doc/ 下）",
)
@click.option(
    "--render",
    type=click.Choice(["none", "first", "all"]),
    default="none",
    show_default=True,
    help="可选：将说明书docx渲染为PNG页图（便于快速验收排版）",
)
@click.option("--render-dpi", type=int, default=140, show_default=True, help="渲染DPI")
@click.option(
    "--render-output-dir",
    default=None,
    type=click.Path(),
    help="PNG输出目录（可选，默认 tmp/docs/pages/<output_stem>/）",
)
@click.pass_context
def explain_doc(ctx, template, output, render, render_dpi, render_output_dir):
    """生成客户可读的“Excel→Docx自动化说明书”（宋体），不包含任何患者级样例值。"""
    from reportgen.core.customer_doc import generate_customer_summary_docx
    from reportgen.utils.docx_render import render_docx_to_pngs

    out_path = Path(output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out = generate_customer_summary_docx(
        template_path=str(Path(template).resolve()),
        config_dir=str(ctx.obj["config_dir"]),
        output_path=str(out_path),
    )

    click.echo(f"Generated: {out}")

    if render != "none":
        pages_dir = (
            Path(render_output_dir).resolve()
            if render_output_dir
            else Path("tmp/docs/pages") / out_path.stem
        )
        pages_dir.mkdir(parents=True, exist_ok=True)

        first_page = 1 if render == "first" else None
        last_page = 1 if render == "first" else None
        pngs = render_docx_to_pngs(
            Path(out),
            output_dir=pages_dir,
            dpi=int(render_dpi),
            keep_pdf=False,
            first_page=first_page,
            last_page=last_page,
        )
        click.echo(f"Rendered pages: {len(pngs)}")
        click.echo(f"Pages dir: {pages_dir.resolve()}")


@cli.command()
@click.option(
    "--template",
    "-t",
    required=True,
    type=click.Path(exists=True),
    help="Docx模板文件路径",
)
@click.option(
    "--show-vars",
    is_flag=True,
    default=False,
    help="显示模板中的所有变量",
)
@click.option(
    "--check-mapping",
    is_flag=True,
    default=False,
    help="校验模板变量是否与mapping配置匹配",
)
@click.pass_context
def validate(ctx, template, show_vars, check_mapping):
    """
    验证模板文件

    示例:

        reportgen validate -t templates/template.docx

        reportgen validate -t templates/template.docx --show-vars

        reportgen validate -t templates/template.docx --check-mapping
    """
    from reportgen.config.loader import ConfigLoader
    from reportgen.core.template_renderer import TemplateRenderer

    log_file = ctx.obj["log_file"]
    config_dir = ctx.obj["config_dir"]

    click.echo(f"🔍 验证模板文件: {template}")

    try:
        renderer = TemplateRenderer(log_file=log_file, log_level=ctx.obj["log_level"])
        is_valid, error = renderer.validate_template(template)

        if not is_valid:
            click.echo(f"❌ 模板文件无效: {error}", err=True)
            sys.exit(1)

        click.echo("✅ 模板文件格式有效")

        # 显示变量
        if show_vars or check_mapping:
            vars_list = renderer.get_template_variables(template)
            single_vars = [v for v in vars_list if not v.startswith("row")]
            row_vars = [v for v in vars_list if v.startswith("row")]

            if show_vars:
                click.echo("\n📋 模板变量统计:")
                click.echo(f"   单值变量: {len(single_vars)}个")
                click.echo(f"   循环变量: {len(row_vars)}个")

                click.echo("\n📌 单值变量列表:")
                for v in sorted(single_vars):
                    click.echo(f"   - {v}")

                click.echo("\n🔄 循环变量列表:")
                for v in sorted(row_vars):
                    click.echo(f"   - {v}")

        # 校验mapping
        if check_mapping:
            config_loader = ConfigLoader(
                config_dir=config_dir, log_file=log_file, log_level=ctx.obj["log_level"]
            )
            mapping_config = config_loader.load_mapping_config()

            # 获取mapping中定义的变量
            available_vars = list(mapping_config.get("single_values", {}).keys())
            available_vars.extend(list(mapping_config.get("table_data", {}).keys()))

            available_row_keys = set()
            for _, table_cfg in mapping_config.get("table_data", {}).items():
                cols = (table_cfg or {}).get("columns", {})
                for col_var, col_cfg in (cols or {}).items():
                    available_row_keys.add(str(col_var))
                    for syn in (col_cfg or {}).get("synonyms", []) or []:
                        available_row_keys.add(str(syn))

            _, missing_vars, unused_vars = renderer.validate_template_variables(
                template, available_vars, available_row_keys=available_row_keys
            )

            click.echo("\n🔗 Mapping配置校验:")
            if missing_vars:
                click.echo(
                    f"   ⚠️  模板中有 {len(missing_vars)} 个变量在mapping中未定义:"
                )
                for v in missing_vars[:10]:
                    click.echo(f"      - {v}")
                if len(missing_vars) > 10:
                    click.echo(f"      ... 还有 {len(missing_vars) - 10} 个")
            else:
                click.echo("   ✅ 所有模板变量都有对应的mapping定义")

            if unused_vars:
                click.echo(
                    f"   ℹ️  mapping中有 {len(unused_vars)} 个变量在模板中未使用"
                )

        sys.exit(0)

    except Exception as e:
        click.echo(f"❌ 验证失败: {e}", err=True)
        sys.exit(1)


@cli.command("validate-config")
@click.pass_context
def validate_config(ctx):
    """校验 config/ 下的 YAML 配置是否满足基础 schema 约束。"""
    from reportgen.config.loader import ConfigLoader
    from reportgen.config.validators import (
        validate_filtering_config,
        validate_mapping_config,
        validate_project_types_config,
        validate_settings_config,
    )

    config_dir = Path(ctx.obj["config_dir"]).resolve()
    loader = ConfigLoader(
        config_dir=str(config_dir),
        log_file=ctx.obj.get("log_file"),
        log_level=ctx.obj.get("log_level") or "INFO",
    )

    checks = [
        ("mapping.yaml", config_dir / "mapping.yaml", validate_mapping_config, True),
        (
            "project_types.yaml",
            config_dir / "project_types.yaml",
            validate_project_types_config,
            True,
        ),
        (
            "settings.yaml",
            config_dir / "settings.yaml",
            validate_settings_config,
            False,
        ),
        (
            "filtering.yaml",
            config_dir / "filtering.yaml",
            validate_filtering_config,
            False,
        ),
    ]

    has_errors = False
    for display, path, validator, required in checks:
        if not path.exists():
            if required:
                click.echo(f"[ERROR] missing: {display} ({path})", err=True)
                has_errors = True
            else:
                click.echo(f"[SKIP] optional missing: {display} ({path})")
            continue

        try:
            cfg = loader.load_yaml(str(path))
        except Exception as e:
            click.echo(f"[ERROR] failed to load: {display} ({e})", err=True)
            has_errors = True
            continue

        ok, errors = validator(cfg)
        if ok:
            click.echo(f"[OK] {display}")
            continue

        has_errors = True
        click.echo(f"[ERROR] {display} schema invalid ({len(errors)}):", err=True)
        for msg in errors:
            click.echo(f"  - {msg}", err=True)

    sys.exit(0 if not has_errors else 1)


@cli.command()
@click.pass_context
def init(ctx):
    """
    初始化项目结构

    创建必要的目录和示例配置文件。
    """
    click.echo("🚀 初始化项目结构...")

    directories = [
        "config",
        "templates",
        "data/input",
        "data/output",
        "data/logs",
    ]

    try:
        for directory in directories:
            path = Path(directory)
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                click.echo(f"✅ 创建目录: {directory}")
            else:
                click.echo(f"⏭️  目录已存在: {directory}")

        click.echo("\n✅ 项目初始化完成!")
        click.echo("\n下一步:")
        click.echo("1. 将Excel文件放入 data/input/ 目录")
        click.echo("2. 将Docx模板放入 templates/ 目录")
        click.echo("3. 运行: reportgen generate \\")
        click.echo("   -e data/input/your_file.xlsx \\")
        click.echo("   -t templates/your_template.docx \\")
        click.echo("   -o data/output/")

        sys.exit(0)

    except Exception as e:
        click.echo(f"❌ 初始化失败: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
