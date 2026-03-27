"""核心业务逻辑包"""

from reportgen.core.data_cleaner import DataCleaner
from reportgen.core.excel_reader import ExcelReader
from reportgen.core.field_mapper import FieldMapper

# 可选依赖：docxtpl（模板渲染/报告生成需要）。
# 允许在未安装docxtpl时仍可使用Excel解析、字段映射、配置校验等能力。
try:
    from reportgen.core.report_generator import ReportGenerator
    from reportgen.core.template_renderer import TemplateRenderer
except ModuleNotFoundError:
    TemplateRenderer = None  # type: ignore[assignment]
    ReportGenerator = None  # type: ignore[assignment]

__all__ = [
    "ExcelReader",
    "FieldMapper",
    "DataCleaner",
]

if TemplateRenderer is not None:
    __all__.append("TemplateRenderer")
if ReportGenerator is not None:
    __all__.append("ReportGenerator")
