"""
Panel enhancer registry.

Dispatches report enhancement to the correct panel-specific enhancer
based on detected project type, decoupling the orchestrator from any
single panel implementation.
"""

from typing import Any, Dict, Optional, Protocol

from reportgen.models.report_data import ReportData


class PanelEnhancer(Protocol):
    """Protocol for panel-specific report enhancers."""

    def enhance(
        self,
        report_data: ReportData,
        excel_data: Any,
        *,
        field_mapper: Any = None,
        gene_knowledge_provider: Any = None,
        base_path: Optional[str] = None,
    ) -> ReportData: ...


class NoopEnhancer:
    """Pass-through enhancer that returns data unchanged.

    Used as default for unknown/unregistered project types.
    """

    def enhance(
        self,
        report_data: ReportData,
        excel_data: Any,
        *,
        field_mapper: Any = None,
        gene_knowledge_provider: Any = None,
        base_path: Optional[str] = None,
    ) -> ReportData:
        return report_data


class CRC358Enhancer:
    """CRC 358/301 panel enhancer.

    Delegates to ``template_bridge_358.enhance_report_data()``.
    Uses lazy import to avoid circular dependencies.
    """

    def enhance(
        self,
        report_data: ReportData,
        excel_data: Any,
        *,
        field_mapper: Any = None,
        gene_knowledge_provider: Any = None,
        base_path: Optional[str] = None,
    ) -> ReportData:
        from reportgen.core.template_bridge_358 import enhance_report_data

        return enhance_report_data(
            report_data,
            excel_data,
            field_mapper=field_mapper,
            gene_knowledge_provider=gene_knowledge_provider,
            base_path=base_path,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_NOOP = NoopEnhancer()

_REGISTRY: Dict[str, PanelEnhancer] = {
    "crc_301_msi": CRC358Enhancer(),
    "crc_358_msi": CRC358Enhancer(),
    # mlf_result: 通用基因检测结果，不注入 CRC 口径
    "mlf_result": _NOOP,
    # lung_methylation 需要独立实现；暂用 Noop 避免注入 CRC 口径
    "lung_methylation": _NOOP,
}


def get_enhancer(project_type: Optional[str] = None) -> PanelEnhancer:
    """Look up the enhancer for a given project type.

    When *project_type* is ``None`` (caller didn't detect or pass a type),
    returns :class:`NoopEnhancer` to avoid注入错误口径的业务逻辑。
    CRC 项目必须通过 auto-detect 显式识别后才走 CRC358Enhancer。
    """
    if project_type is None:
        return _NOOP
    return _REGISTRY.get(project_type, _NOOP)


def register_enhancer(project_type: str, enhancer: PanelEnhancer) -> None:
    """Register a custom enhancer for a project type."""
    _REGISTRY[project_type] = enhancer
