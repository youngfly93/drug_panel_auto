"""
配置加载器模块

负责加载和解析YAML配置文件。
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from reportgen.config.validators import (
    validate_filtering_config as validate_filtering_config_schema,
)
from reportgen.config.validators import (
    validate_mapping_config as validate_mapping_config_schema,
)
from reportgen.config.validators import (
    validate_project_types_config as validate_project_types_config_schema,
)
from reportgen.config.validators import (
    validate_settings_config as validate_settings_config_schema,
)
from reportgen.utils.logger import get_logger


class ConfigLoader:
    """
    配置加载器

    加载和验证mapping.yaml, project_types.yaml, settings.yaml等配置文件。
    """

    def __init__(
        self,
        config_dir: str = "config",
        log_file: Optional[str] = None,
        log_level: str = "INFO",
    ):
        """
        初始化配置加载器

        Args:
            config_dir: 配置文件目录路径
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.config_dir = Path(config_dir).resolve()
        # 项目根目录 = config_dir 的父目录（如 config/ -> 项目根）
        self.project_root = self.config_dir.parent
        self.logger = get_logger(log_file=log_file, level=log_level)

        # 配置缓存
        self._mapping_config: Optional[Dict] = None
        self._project_types_config: Optional[Dict] = None
        self._settings_config: Optional[Dict] = None
        self._filtering_config: Optional[Dict] = None

    def load_yaml(self, file_path: str) -> Dict[str, Any]:
        """
        加载YAML文件

        Args:
            file_path: YAML文件路径

        Returns:
            解析后的配置字典

        Raises:
            FileNotFoundError: 如果文件不存在
            yaml.YAMLError: 如果YAML格式错误
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if config is None:
                return {}

            self.logger.debug(
                "成功加载配置文件",
                file=str(file_path),
                keys=len(config) if isinstance(config, dict) else 0,
            )

            return config

        except yaml.YAMLError as e:
            self.logger.error("YAML格式错误", file=str(file_path), error=str(e))
            raise

    def load_mapping_config(self, reload: bool = False) -> Dict[str, Any]:
        """
        加载字段映射配置

        Args:
            reload: 是否强制重新加载（忽略缓存）

        Returns:
            映射配置字典
        """
        if self._mapping_config is not None and not reload:
            return self._mapping_config

        mapping_file = self.config_dir / "mapping.yaml"
        config = self.load_yaml(str(mapping_file))

        ok, errors = validate_mapping_config_schema(config)
        if not ok:
            joined = "\n".join([f"- {e}" for e in errors])
            raise ValueError(f"mapping.yaml schema校验失败:\n{joined}")

        self._mapping_config = config

        self.logger.info(
            "字段映射配置加载成功",
            single_values_count=len(config.get("single_values", {})),
            table_data_count=len(config.get("table_data", {})),
        )

        return config

    def load_project_types_config(self, reload: bool = False) -> Dict[str, Any]:
        """
        加载项目类型配置

        Args:
            reload: 是否强制重新加载

        Returns:
            项目类型配置字典
        """
        if self._project_types_config is not None and not reload:
            return self._project_types_config

        types_file = self.config_dir / "project_types.yaml"
        config = self.load_yaml(str(types_file))

        ok, errors = validate_project_types_config_schema(config)
        if not ok:
            joined = "\n".join([f"- {e}" for e in errors])
            raise ValueError(f"project_types.yaml schema校验失败:\n{joined}")

        self._project_types_config = config

        self.logger.info(
            "项目类型配置加载成功",
            project_types_count=len(config.get("project_types") or []),
        )

        return config

    def load_settings_config(self, reload: bool = False) -> Dict[str, Any]:
        """
        加载全局设置配置

        Args:
            reload: 是否强制重新加载

        Returns:
            设置配置字典
        """
        if self._settings_config is not None and not reload:
            return self._settings_config

        settings_file = self.config_dir / "settings.yaml"

        # settings.yaml是可选的，如果不存在返回空配置
        if not settings_file.exists():
            self.logger.warning(
                "全局设置文件不存在，使用默认配置", file=str(settings_file)
            )
            return {}

        config = self.load_yaml(str(settings_file))
        ok, errors = validate_settings_config_schema(config)
        if not ok:
            joined = "\n".join([f"- {e}" for e in errors])
            raise ValueError(f"settings.yaml schema校验失败:\n{joined}")
        self._settings_config = config

        self.logger.info("全局设置配置加载成功")

        return config

    def load_filtering_config(self, reload: bool = False) -> Dict[str, Any]:
        """
        加载数据过滤配置

        Args:
            reload: 是否强制重新加载

        Returns:
            过滤配置字典
        """
        if self._filtering_config is not None and not reload:
            return self._filtering_config

        filtering_file = self.config_dir / "filtering.yaml"

        # filtering.yaml是可选的，如果不存在返回默认配置
        if not filtering_file.exists():
            self.logger.warning(
                "过滤配置文件不存在，使用默认配置", file=str(filtering_file)
            )
            # 返回默认配置
            default_cfg = {
                "variations": {
                    "enabled": True,
                    "frequency_filter": {
                        "enabled": True,
                        "min_frequency": 5.0,
                        "frequency_columns": [
                            "Freq(%)",
                            "AF",
                            "变异频率",
                            "Frequency",
                            "freq",
                        ],
                    },
                    "clinical_significance_filter": {
                        "enabled": True,
                        "significant_keywords": [
                            "Missense",
                            "Nonsense",
                            "Frameshift",
                            "Splice",
                        ],
                        "function_columns": [
                            "Function",
                            "功能",
                            "Type",
                            "变异类型",
                            "Consequence",
                        ],
                    },
                }
            }
            ok, errors = validate_filtering_config_schema(default_cfg)
            if not ok:
                joined = "\n".join([f"- {e}" for e in errors])
                raise ValueError(f"内置 filtering.yaml 默认配置不合法:\n{joined}")
            return default_cfg

        config = self.load_yaml(str(filtering_file))
        ok, errors = validate_filtering_config_schema(config)
        if not ok:
            joined = "\n".join([f"- {e}" for e in errors])
            raise ValueError(f"filtering.yaml schema校验失败:\n{joined}")
        self._filtering_config = config

        self.logger.info("过滤配置加载成功")

        return config

    def get_mapping_for_variable(
        self, variable_name: str, is_table: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        获取指定变量的映射配置

        Args:
            variable_name: 变量名
            is_table: 是否是表格数据

        Returns:
            映射配置字典，如果不存在返回None
        """
        config = self.load_mapping_config()

        if is_table:
            return config.get("table_data", {}).get(variable_name)
        else:
            return config.get("single_values", {}).get(variable_name)

    def get_project_types(self) -> list[Dict[str, Any]]:
        """
        获取所有项目类型定义

        Returns:
            项目类型列表
        """
        config = self.load_project_types_config()
        return config.get("project_types", [])

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        获取设置值

        Args:
            key: 设置键（支持点号分隔的路径，如 'logging.level'）
            default: 默认值

        Returns:
            设置值
        """
        # 环境变量覆盖：REPORTGEN_<SECTION>_<KEY>
        # 例如 key='logging.level' -> REPORTGEN_LOGGING_LEVEL
        env_key = "REPORTGEN_" + "_".join(
            [p.strip().upper() for p in key.split(".") if p.strip()]
        )
        if env_key in os.environ:
            raw = os.environ.get(env_key)
            try:
                return yaml.safe_load(raw)
            except Exception:
                return raw

        config = self.load_settings_config()

        # 支持嵌套键（如 'logging.level'）
        keys = key.split(".")
        value = config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value

    def validate_mapping_config(self) -> tuple[bool, list[str]]:
        """
        验证映射配置的完整性

        Returns:
            (是否有效, 错误消息列表)
        """
        try:
            config = self.load_mapping_config()
        except Exception as e:
            return False, [f"配置加载失败: {e}"]
        return validate_mapping_config_schema(config)

    def load_patient_info(
        self,
        sample_id: Optional[str] = None,
        *,
        include_project_info: bool = True,
    ) -> Dict[str, Any]:
        """
        加载患者信息配置

        Args:
            sample_id: 样本编号，用于匹配特定患者信息
            include_project_info: 是否包含全局 project_info（detector 等不应拿到，
                避免把未知样本误判为固定项目类型）

        Returns:
            患者信息字典
        """
        patient_info_file = self.config_dir / "patient_info.yaml"

        if not patient_info_file.exists():
            self.logger.warning("患者信息配置文件不存在", file=str(patient_info_file))
            return {}

        try:
            config = self.load_yaml(str(patient_info_file))

            # 先加载默认值（hospital, department 等通用信息）
            defaults = config.get("defaults", {})
            result = dict(defaults)

            # project_info（含 project_name）仅在显式请求时合并
            if include_project_info:
                project_info = config.get("project_info", {})
                result.update(project_info)

            # 如果有样本编号，尝试匹配特定患者信息
            if sample_id:
                patients = config.get("patients", {})
                patient_data = patients.get(sample_id)

                if patient_data:
                    result.update(patient_data)
                    self.logger.info(
                        "找到匹配的患者信息",
                        sample_id=sample_id,
                        source="patient_info.yaml",
                    )
                else:
                    self.logger.warning(
                        "未找到匹配的患者信息",
                        sample_id=sample_id,
                        available_keys=list(patients.keys()),
                    )

            return result

        except Exception as e:
            self.logger.error("加载患者信息失败", error=str(e))
            return {}

    def resolve_path(self, relative_path: str) -> Path:
        """将配置中的相对路径解析为基于项目根目录的绝对路径。

        如果路径本身已是绝对路径则原样返回。

        Args:
            relative_path: 配置中的相对路径（如 "templates/xxx.docx"）

        Returns:
            解析后的绝对路径
        """
        p = Path(str(relative_path))
        if p.is_absolute():
            return p
        return self.project_root / p
