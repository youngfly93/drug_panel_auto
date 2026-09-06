"""
项目类型检测器

根据Excel文件名和内容自动识别项目类型。
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from reportgen.config.loader import ConfigLoader
from reportgen.panels.loader import PanelPackageLoader
from reportgen.utils.logger import get_logger


class ProjectDetector:
    """
    项目类型检测器

    根据Excel文件名、内容和配置规则自动识别项目类型，
    并返回对应的模板路径。
    """

    def __init__(
        self,
        config_dir: str = "config",
        log_file: Optional[str] = None,
        log_level: str = "INFO",
    ):
        """
        初始化检测器

        Args:
            config_dir: 配置目录
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.config_dir = config_dir
        self.logger = get_logger(log_file=log_file, level=log_level)

        # 加载项目类型配置
        self._config_loader = ConfigLoader(
            config_dir=config_dir, log_file=log_file, log_level=log_level
        )
        self.config = self._config_loader.load_project_types_config()
        self.mapping_config = self._config_loader.load_mapping_config()

        self.project_types = self._merge_panel_project_types(
            self.config.get("project_types", [])
        )
        self.default_config = self.config.get("default", {})

    def _merge_panel_project_types(
        self,
        configured_types: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge project detector rules declared by panel packages.

        Existing ``config/project_types.yaml`` entries stay as a compatibility
        fallback, while package declarations become the canonical source for
        active panel ids.
        """
        by_id = {
            str(item.get("id") or "").strip(): dict(item)
            for item in configured_types
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        try:
            packages = PanelPackageLoader(
                project_root=self._config_loader.project_root
            ).load_all()
        except Exception:
            return list(by_id.values())

        for package in packages:
            rules = package.project_detector_rules or {}
            if not rules:
                continue
            entry = dict(by_id.get(package.panel_id, {}))
            try:
                template_file = str(package.resolve_template_file())
            except Exception:
                template_file = str(entry.get("template") or "")
            entry.update(
                {
                    "id": package.panel_id,
                    "name": package.display_name,
                    "keywords": list(
                        rules.get("keywords") or entry.get("keywords") or []
                    ),
                    "keyword_groups": list(
                        rules.get("keyword_groups") or entry.get("keyword_groups") or []
                    ),
                    "structural_fingerprints": list(
                        rules.get("structural_fingerprints")
                        or entry.get("structural_fingerprints")
                        or []
                    ),
                    "identity_family": dict(rules.get("identity_family") or {}),
                    "template": template_file,
                    "priority": rules.get("priority", entry.get("priority", 10)),
                    "description": package.raw.get("description")
                    or entry.get("description")
                    or package.display_name,
                }
            )
            by_id[package.panel_id] = entry

        return list(by_id.values())

    def identity_family_id(self, project_type: str) -> str:
        """Return a declared NGS identity family; undeclared panels stay distinct."""
        for entry in self.project_types:
            if entry["id"] == project_type:
                return str((entry.get("identity_family") or {}).get("id") or project_type)
        return project_type

    def _resolve_structural_family(self, structural_types, detection_text, threshold):
        """NGS headers identify a family, never the presence of an IHC order.

        Only trusted project/order text may select an IHC variant automatically.
        A filename (including a derived-input suffix) cannot supply that evidence.
        """
        families = {self.identity_family_id(value) for value in structural_types}
        if len(families) != 1:
            return None, [], None
        members = [entry for entry in self.project_types if entry["id"] in structural_types]
        defaults = {
            (entry.get("identity_family") or {}).get("default_project_type")
            for entry in members
        }
        if len(defaults) != 1 or None in defaults:
            return None, [], None
        default = next((entry for entry in members if entry["id"] in defaults), None)
        if default is None:
            return None, [], None
        text_matches = [
            entry for entry in members
            if detection_text and self._calculate_match_score(entry, "", detection_text)[0] >= threshold
        ]
        selected = text_matches[0] if len(text_matches) == 1 else default
        choices = [{"id": entry["id"], "name": entry["name"]} for entry in members]
        source = "trusted_project_text" if len(text_matches) == 1 else "ngs_family_default"
        return selected, choices, source

    def detect(
        self,
        excel_path: str,
        excel_data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        检测项目类型

        Args:
            excel_path: Excel文件路径
            excel_data: 可选的已读取Excel数据（用于内容匹配）

        Returns:
            检测结果字典:
                - detected: 是否成功检测
                - project_type: 项目类型ID
                - project_name: 项目类型名称
                - template: 推荐模板路径
                - confidence: 匹配置信度 (0-1)
                - match_details: 匹配详情
        """
        filename = Path(excel_path).name
        detection_text = self._extract_detection_text(excel_data)

        best_match = None
        best_score = 0.0
        best_priority = float("-inf")
        match_details = []

        for ptype in self.project_types:
            score, details = self._calculate_match_score(
                ptype,
                filename,
                detection_text,
                excel_data=excel_data,
            )
            priority = float(ptype.get("priority", 0) or 0)
            match_details.append(
                {
                    "type": ptype["id"],
                    "name": ptype["name"],
                    "score": score,
                    "priority": priority,
                    "details": details,
                }
            )

            if score > best_score or (score == best_score and priority > best_priority):
                best_score = score
                best_priority = priority
                best_match = ptype

        threshold = self.default_config.get("match_threshold", 0.6)
        structural_types = {
            str(match.get("type") or "").strip()
            for match in match_details
            if any(
                str(detail).startswith("结构指纹匹配:")
                for detail in match.get("details") or []
            )
        }
        high_confidence_types = {
            str(match.get("type") or "").strip()
            for match in match_details
            if float(match.get("score") or 0) >= threshold
        }
        identity_conflicts = sorted(
            item for item in structural_types | high_confidence_types if item
        )
        if not structural_types or len({self.identity_family_id(value) for value in identity_conflicts}) < 2:
            identity_conflicts = []

        family_match, family_choices, identity_source = self._resolve_structural_family(
            structural_types, detection_text, threshold
        )
        if family_match is not None:
            best_match = family_match
            best_score = max(best_score, threshold)

        if best_match and best_score >= threshold:
            result = {
                "detected": True,
                "project_type": best_match["id"],
                "project_name": best_match["name"],
                "template": best_match.get("template"),
                "confidence": best_score,
                "match_details": match_details,
                "identity_conflicts": identity_conflicts,
                "identity_family": self.identity_family_id(best_match["id"]),
                "family_choices": family_choices,
                "identity_source": identity_source,
            }
            self.logger.info(
                "项目类型检测成功",
                project_type=best_match["id"],
                confidence=f"{best_score:.2f}",
            )
        else:
            result = {
                "detected": False,
                "project_type": None,
                "project_name": None,
                "template": self.default_config.get("template"),
                "confidence": best_score,
                "match_details": match_details,
                "identity_conflicts": identity_conflicts,
            }
            self.logger.warning(
                "项目类型检测失败，使用默认模板",
                best_score=f"{best_score:.2f}",
                threshold=threshold,
            )

        # Ensure the resolved template exists; if not, fall back to a safe default.
        # 使用 config_loader.resolve_path 将相对路径基于项目根目录解析
        warnings: List[str] = []
        template = result.get("template")
        if template:
            resolved = self._config_loader.resolve_path(str(template))
            if resolved.exists():
                result["template"] = str(resolved)
            else:
                warnings.append(f"template_not_found:{template}")

                candidates = [
                    self.default_config.get("template"),
                    "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx",
                ]
                fallback = None
                for cand in candidates:
                    if not cand:
                        continue
                    cand_resolved = self._config_loader.resolve_path(str(cand))
                    if cand_resolved.exists():
                        fallback = str(cand_resolved)
                        break

                if fallback:
                    warnings.append(f"template_fallback:{fallback}")
                    result["template"] = fallback
                    self.logger.warning(
                        "检测到的模板文件不存在，已回退到可用模板",
                        missing_template=str(template),
                        fallback_template=str(fallback),
                    )
                else:
                    warnings.append("no_valid_template_available")
                    result["template"] = None
                    self.logger.error(
                        "无法找到任何可用模板（检测模板与默认模板均不存在）",
                        missing_template=str(template),
                    )

        if warnings:
            result["warnings"] = warnings

        return result

    def _calculate_match_score(
        self,
        project_type: Dict[str, Any],
        filename: str,
        detection_text: Optional[str],
        excel_data: Optional[Any] = None,
    ) -> tuple[float, List[str]]:
        """
        计算项目类型匹配分数

        Args:
            project_type: 项目类型配置
            filename: 文件名（小写）
            excel_data: Excel数据

        Returns:
            (匹配分数, 匹配详情列表)
        """
        structural_score, structural_details = (
            self._calculate_structural_fingerprint_score(project_type, excel_data)
        )
        keyword_groups = project_type.get("keyword_groups")
        if keyword_groups:
            text_score, text_details = self._calculate_group_match_score(
                project_type, filename, detection_text
            )
            if structural_score > text_score:
                return structural_score, structural_details
            if structural_score == text_score and structural_score > 0:
                return structural_score, [*text_details, *structural_details]
            return text_score, text_details

        # 兼容旧配置：keywords 为简单字符串列表（按“命中数/总数”计算）
        keywords = project_type.get("keywords", [])
        if not keywords:
            return structural_score, structural_details

        case_sensitive = self.default_config.get("case_sensitive", False)
        matched_in_filename = set()

        for keyword in keywords:
            kw = keyword if case_sensitive else keyword.lower()
            target = filename if case_sensitive else filename.lower()

            if kw in target:
                matched_in_filename.add(keyword)

        # 基于文件名的匹配分数
        details = []
        if matched_in_filename:
            details.append(
                f"文件名匹配关键词: {', '.join(sorted(matched_in_filename))}"
            )

        matched = set(matched_in_filename)
        if detection_text:
            content_matches, content_details = self._check_excel_content(
                project_type, detection_text
            )
            matched |= set(content_matches)
            details.extend(content_details)

        text_score = len(matched) / len(keywords) if keywords else 0.0
        if structural_score > text_score:
            return structural_score, structural_details
        if structural_score == text_score and structural_score > 0:
            return structural_score, [*details, *structural_details]
        return text_score, details

    def _calculate_structural_fingerprint_score(
        self,
        project_type: Dict[str, Any],
        excel_data: Optional[Any],
    ) -> tuple[float, List[str]]:
        """Match allowlisted table/column fingerprints declared by a Panel.

        Only table names and column headers participate. Cell values are
        intentionally excluded so generic numbers such as ``358`` or ``588``
        cannot route a case to the wrong cancer product.
        """
        fingerprints = project_type.get("structural_fingerprints") or []
        if excel_data is None or not isinstance(fingerprints, list):
            return 0.0, []

        table_data = getattr(excel_data, "table_data", None)
        if table_data is None and isinstance(excel_data, dict):
            table_data = excel_data.get("table_data")
        if not isinstance(table_data, dict):
            return 0.0, []

        best_score = 0.0
        best_id = ""
        for index, fingerprint in enumerate(fingerprints, start=1):
            if not isinstance(fingerprint, dict):
                continue
            required_tables = fingerprint.get("required_tables")
            if not isinstance(required_tables, dict) or not required_tables:
                continue

            matched = True
            for table_name, table_contract in required_tables.items():
                rows = table_data.get(str(table_name))
                columns = self._table_columns(rows)
                if not columns:
                    matched = False
                    break
                if isinstance(table_contract, dict):
                    required_columns = table_contract.get("required_columns") or []
                elif isinstance(table_contract, list):
                    required_columns = table_contract
                else:
                    matched = False
                    break
                normalized_required = {
                    str(column).strip().lower()
                    for column in required_columns
                    if str(column or "").strip()
                }
                if not normalized_required or not normalized_required.issubset(columns):
                    matched = False
                    break

            if not matched:
                continue
            confidence = float(fingerprint.get("confidence", 1.0) or 1.0)
            confidence = min(1.0, max(0.0, confidence))
            if confidence > best_score:
                best_score = confidence
                best_id = str(
                    fingerprint.get("id") or f"structural_fingerprint_{index}"
                ).strip()

        if not best_score:
            return 0.0, []
        return best_score, [f"结构指纹匹配: {best_id}"]

    @staticmethod
    def _table_columns(rows: Any) -> set[str]:
        """Return normalized column names without exposing row values."""
        raw_columns: set[Any] = set()
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    raw_columns.update(row.keys())
        else:
            columns = getattr(rows, "columns", None)
            if columns is not None:
                raw_columns.update(columns)
        return {
            str(column).strip().lower()
            for column in raw_columns
            if str(column or "").strip()
        }

    def _calculate_group_match_score(
        self,
        project_type: Dict[str, Any],
        filename: str,
        detection_text: Optional[str],
    ) -> tuple[float, List[str]]:
        """支持 keyword_groups 的匹配模式：按“组”进行 OR/AND 匹配，再做加权汇总。

        project_types.yaml 示例：
          keyword_groups:
            - any: ["358基因", "结直肠癌358", "358"]
              weight: 1
            - any:
                - {type: regex, pattern: "\\\\bMSI\\\\b"}
        """
        groups = project_type.get("keyword_groups") or []
        if not isinstance(groups, list):
            return 0.0, []

        case_sensitive_default = bool(self.default_config.get("case_sensitive", False))
        total_weight = 0.0
        matched_weight = 0.0
        details: List[str] = []

        for idx, group in enumerate(groups, start=1):
            matched, group_details, weight = self._match_keyword_group(
                group,
                filename=filename,
                detection_text=detection_text,
                case_sensitive_default=case_sensitive_default,
                group_index=idx,
            )
            if weight <= 0:
                continue

            total_weight += weight
            if matched:
                matched_weight += weight
            details.extend(group_details)

        score = matched_weight / total_weight if total_weight else 0.0
        return score, details

    KeywordPattern = Union[str, Dict[str, Any]]

    def _match_keyword_group(
        self,
        group: Any,
        *,
        filename: str,
        detection_text: Optional[str],
        case_sensitive_default: bool,
        group_index: int,
    ) -> Tuple[bool, List[str], float]:
        if group is None:
            return False, [], 0.0

        if isinstance(group, list):
            group_cfg: Dict[str, Any] = {"any": group}
        elif isinstance(group, dict):
            group_cfg = group
        else:
            return (
                False,
                [f"组{group_index}: 配置格式无效({type(group).__name__})"],
                0.0,
            )

        weight = float(group_cfg.get("weight", 1) or 1)
        if weight <= 0:
            return False, [], 0.0

        case_sensitive = bool(group_cfg.get("case_sensitive", case_sensitive_default))
        sources = group_cfg.get("sources", "both")
        sources_set = self._normalize_sources(sources)

        any_patterns = self._normalize_patterns(group_cfg.get("any"))
        all_patterns = self._normalize_patterns(group_cfg.get("all"))

        matched_any, matched_any_where = self._match_any_patterns(
            any_patterns,
            filename=filename,
            detection_text=detection_text,
            sources=sources_set,
            case_sensitive=case_sensitive,
        )
        matched_all, matched_all_where = self._match_all_patterns(
            all_patterns,
            filename=filename,
            detection_text=detection_text,
            sources=sources_set,
            case_sensitive=case_sensitive,
        )

        matched = True
        if any_patterns:
            matched = matched and bool(matched_any)
        if all_patterns:
            matched = matched and matched_all

        details: List[str] = []
        if any_patterns:
            if matched_any:
                details.append(
                    f"组{group_index}: 任一匹配({', '.join(matched_any)}) "
                    f"[{matched_any_where}]"
                )
            else:
                details.append(f"组{group_index}: 任一未命中")
        if all_patterns:
            if matched_all:
                details.append(f"组{group_index}: 全部匹配 [{matched_all_where}]")
            else:
                details.append(f"组{group_index}: 全部未命中")

        if not any_patterns and not all_patterns:
            details.append(f"组{group_index}: 未配置 any/all")
            matched = False

        return matched, details, weight

    def _normalize_sources(self, sources: Any) -> set[str]:
        if sources is None or sources == "both":
            return {"filename", "content"}
        if isinstance(sources, str):
            s = sources.strip().lower()
            if s in {"filename", "file"}:
                return {"filename"}
            if s in {"content", "excel", "text"}:
                return {"content"}
            return {"filename", "content"}
        if isinstance(sources, list):
            normalized: set[str] = set()
            for item in sources:
                normalized |= self._normalize_sources(item)
            return normalized or {"filename", "content"}
        return {"filename", "content"}

    def _normalize_patterns(self, patterns: Any) -> List[KeywordPattern]:
        if patterns is None:
            return []
        if isinstance(patterns, (str, dict)):
            return [patterns]
        if isinstance(patterns, list):
            return [p for p in patterns if isinstance(p, (str, dict))]
        return []

    def _pattern_display(self, pattern: KeywordPattern) -> str:
        if isinstance(pattern, str):
            return pattern
        if isinstance(pattern, dict):
            return str(pattern.get("pattern") or pattern.get("value") or "")
        return str(pattern)

    def _pattern_matches(
        self, pattern: KeywordPattern, text: str, *, case_sensitive: bool
    ) -> bool:
        if not text:
            return False

        if isinstance(pattern, str):
            if case_sensitive:
                return pattern in text
            return pattern.lower() in text.lower()

        if not isinstance(pattern, dict):
            return False

        p = pattern.get("pattern") or pattern.get("value")
        if not p:
            return False

        match_type = str(pattern.get("type", "contains")).strip().lower()
        if match_type == "regex":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return re.search(str(p), text, flags=flags) is not None
            except re.error:
                return False

        # default: contains
        if case_sensitive:
            return str(p) in text
        return str(p).lower() in text.lower()

    def _match_any_patterns(
        self,
        patterns: Iterable[KeywordPattern],
        *,
        filename: str,
        detection_text: Optional[str],
        sources: set[str],
        case_sensitive: bool,
    ) -> tuple[List[str], str]:
        matched: List[str] = []
        where: set[str] = set()

        for pattern in patterns:
            disp = self._pattern_display(pattern)
            if "filename" in sources and self._pattern_matches(
                pattern, filename, case_sensitive=case_sensitive
            ):
                matched.append(disp)
                where.add("filename")
                continue

            if (
                "content" in sources
                and detection_text
                and self._pattern_matches(
                    pattern, detection_text, case_sensitive=case_sensitive
                )
            ):
                matched.append(disp)
                where.add("content")

        return matched, "+".join(sorted(where)) or "-"

    def _match_all_patterns(
        self,
        patterns: Iterable[KeywordPattern],
        *,
        filename: str,
        detection_text: Optional[str],
        sources: set[str],
        case_sensitive: bool,
    ) -> tuple[bool, str]:
        if not patterns:
            return True, "-"

        where: set[str] = set()
        for pattern in patterns:
            in_filename = "filename" in sources and self._pattern_matches(
                pattern, filename, case_sensitive=case_sensitive
            )
            in_content = (
                "content" in sources
                and detection_text
                and self._pattern_matches(
                    pattern, detection_text, case_sensitive=case_sensitive
                )
            )

            if not (in_filename or in_content):
                return False, "-"

            if in_filename:
                where.add("filename")
            if in_content:
                where.add("content")

        return True, "+".join(sorted(where)) or "-"

    def _check_excel_content(
        self,
        project_type: Dict[str, Any],
        detection_text: str,
    ) -> tuple[List[str], List[str]]:
        """
        检查Excel内容匹配

        Args:
            project_type: 项目类型配置
            excel_data: Excel数据

        Returns:
            (内容匹配分数, 匹配详情)
        """
        keywords = project_type.get("keywords", [])
        case_sensitive = self.default_config.get("case_sensitive", False)

        # 只使用检测字段文本进行搜索，避免将整表转成超大字符串
        content_str = str(detection_text)
        if not case_sensitive:
            content_str = content_str.lower()

        matched: List[str] = []
        for keyword in keywords:
            kw = keyword if case_sensitive else keyword.lower()
            if kw in content_str:
                matched.append(keyword)

        if matched:
            details = [f"内容匹配关键词: {', '.join(matched)}"]
            return matched, details

        return [], []

    def _extract_detection_text(self, excel_data: Optional[Any]) -> Optional[str]:
        """从Excel读取结果中提取用于项目识别的文本。

        优先取 project_types.yaml:default.detection_field（如 project_name）的值，
        若不存在则回退到：单值字段 + sheet_names + (关键表的列名) 的组合文本。
        """
        if excel_data is None:
            return None

        # ExcelDataSource 或者类似结构
        single_values = getattr(excel_data, "single_values", None)
        if single_values is None and isinstance(excel_data, dict):
            single_values = excel_data

        if not isinstance(single_values, dict):
            return str(excel_data)

        detection_field = self.default_config.get("detection_field")
        if detection_field:
            field_cfg = (self.mapping_config.get("single_values", {}) or {}).get(
                detection_field, {}
            )
            synonyms = (
                field_cfg.get("synonyms", []) if isinstance(field_cfg, dict) else []
            )
            candidates = [detection_field, *synonyms]

            for cand in candidates:
                cand_norm = str(cand).strip().lower()
                for k, v in single_values.items():
                    if str(k).strip().lower() == cand_norm:
                        return None if v is None else str(v)

            # 回退：仅当 Excel 提供了可匹配的样本编号时，才从 patient_info.yaml 获取项目信息。
            # 不使用全局 project_info 作为硬兜底，避免把未知样本误判为固定项目类型。
            sample_id = None
            metadata = getattr(excel_data, "metadata", None)
            if isinstance(metadata, dict):
                sample_id = metadata.get("sample_id_from_filename")
            if sample_id:
                try:
                    patient_info = self._config_loader.load_patient_info(
                        sample_id, include_project_info=False
                    )
                    pi_val = patient_info.get(detection_field)
                    if pi_val is not None and str(pi_val).strip():
                        return str(pi_val)
                except Exception:
                    pass

        # Do not fall back to the full single_values dict, sheet names, or table
        # columns. Generic columns such as ExistInsmall358 contain panel numbers
        # and caused false CRC project detection. If no trusted project field is
        # available, project detection should rely on the filename or user input.
        return None

    def get_available_project_types(self) -> List[Dict[str, str]]:
        """
        获取所有可用的项目类型

        Returns:
            项目类型列表 [{id, name, description}]
        """
        return [
            {
                "id": pt["id"],
                "name": pt["name"],
                "description": pt.get("description", ""),
            }
            for pt in self.project_types
        ]

    def get_template_for_type(self, project_type_id: str) -> Optional[str]:
        """
        获取指定项目类型的模板路径

        Args:
            project_type_id: 项目类型ID

        Returns:
            模板路径，或None（未找到）
        """
        for pt in self.project_types:
            if pt["id"] == project_type_id:
                return pt.get("template")
        return None
