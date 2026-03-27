"""
结构化日志模块

提供JSON格式的结构化日志，支持操作审计和问题追溯。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class StructuredLogger:
    """
    结构化日志记录器

    使用JSON格式记录日志，便于机器解析和分析。
    支持控制台和文件双输出。
    """

    def __init__(
        self,
        name: str = "reportgen",
        log_file: Optional[str] = None,
        level: str = "INFO",
        console_output: bool = True,
        json_format: bool = True,
    ):
        """
        初始化日志记录器

        Args:
            name: 日志记录器名称
            log_file: 日志文件路径，None表示不输出到文件
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
            console_output: 是否输出到控制台
            json_format: 是否使用JSON格式
        """
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        self.json_format = bool(json_format)
        self.configure(
            log_file=log_file,
            level=level,
            console_output=console_output,
            json_format=json_format,
        )

    def configure(
        self,
        *,
        log_file: Optional[str],
        level: str,
        console_output: bool,
        json_format: bool,
    ) -> None:
        """Idempotently configure handlers for the underlying logger."""
        self.json_format = bool(json_format)
        try:
            level_int = getattr(logging, str(level).upper())
        except Exception:
            level_int = logging.INFO

        self.logger.setLevel(level_int)

        desired_log_file: Optional[Path] = None
        if log_file:
            desired_log_file = Path(str(log_file)).expanduser().resolve()
            desired_log_file.parent.mkdir(parents=True, exist_ok=True)

        # Remove outdated/disabled reportgen-managed handlers.
        for h in list(self.logger.handlers):
            if not getattr(h, "_reportgen_handler", False):
                continue

            if isinstance(h, logging.FileHandler):
                if desired_log_file is None:
                    self.logger.removeHandler(h)
                    try:
                        h.close()
                    except Exception:
                        pass
                    continue

                current = getattr(h, "baseFilename", None)
                try:
                    current_path = Path(str(current)).resolve() if current else None
                except Exception:
                    current_path = None
                if current_path != desired_log_file:
                    self.logger.removeHandler(h)
                    try:
                        h.close()
                    except Exception:
                        pass
                continue

            # Stream handler (console)
            if not console_output:
                self.logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

        formatter = (
            self._json_formatter() if self.json_format else self._text_formatter()
        )

        # Ensure console handler (at most one).
        if console_output:
            console_handler: Optional[logging.Handler] = None
            for h in self.logger.handlers:
                if (
                    getattr(h, "_reportgen_handler", False)
                    and isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)
                ):
                    console_handler = h
                    break

            if console_handler is None:
                console_handler = logging.StreamHandler()
                console_handler._reportgen_handler = True  # type: ignore[attr-defined]
                self.logger.addHandler(console_handler)

            console_handler.setLevel(level_int)
            console_handler.setFormatter(formatter)

        # Ensure file handler (at most one, for the desired path).
        if desired_log_file is not None:
            file_handler: Optional[logging.Handler] = None
            for h in self.logger.handlers:
                if not (
                    getattr(h, "_reportgen_handler", False)
                    and isinstance(h, logging.FileHandler)
                ):
                    continue
                current = getattr(h, "baseFilename", None)
                try:
                    current_path = Path(str(current)).resolve() if current else None
                except Exception:
                    current_path = None
                if current_path == desired_log_file:
                    file_handler = h
                    break

            if file_handler is None:
                file_handler = logging.FileHandler(
                    str(desired_log_file), encoding="utf-8"
                )
                file_handler._reportgen_handler = True  # type: ignore[attr-defined]
                self.logger.addHandler(file_handler)

            file_handler.setLevel(level_int)
            file_handler.setFormatter(formatter)

    def _json_formatter(self) -> logging.Formatter:
        """创建JSON格式化器"""
        return logging.Formatter("%(message)s")

    def _text_formatter(self) -> logging.Formatter:
        """创建文本格式化器"""
        return logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

    def _format_json_message(self, level: str, message: str, **kwargs: Any) -> str:
        """
        格式化JSON日志消息

        Args:
            level: 日志级别
            message: 日志消息
            **kwargs: 额外的上下文数据

        Returns:
            JSON格式的日志字符串
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }
        return json.dumps(log_entry, ensure_ascii=False)

    def log_event(self, event_type: str, level: str = "INFO", **kwargs: Any) -> None:
        """
        记录结构化事件

        Args:
            event_type: 事件类型（如 'report_generated', 'excel_parsed'）
            level: 日志级别
            **kwargs: 事件相关的上下文数据
        """
        if self.json_format:
            message = self._format_json_message(
                level=level, message=event_type, event_type=event_type, **kwargs
            )
        else:
            # 文本格式：event_type: key1=value1, key2=value2
            context = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            message = f"{event_type}: {context}" if context else event_type

        log_method = getattr(self.logger, level.lower())
        log_method(message)

    def info(self, message: str, **kwargs: Any) -> None:
        """记录INFO级别日志"""
        if self.json_format:
            message = self._format_json_message("INFO", message, **kwargs)
        self.logger.info(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """记录DEBUG级别日志"""
        if self.json_format:
            message = self._format_json_message("DEBUG", message, **kwargs)
        self.logger.debug(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        """记录WARNING级别日志"""
        if self.json_format:
            message = self._format_json_message("WARNING", message, **kwargs)
        self.logger.warning(message)

    def error(self, message: str, **kwargs: Any) -> None:
        """记录ERROR级别日志"""
        if self.json_format:
            message = self._format_json_message("ERROR", message, **kwargs)
        self.logger.error(message)

    def critical(self, message: str, **kwargs: Any) -> None:
        """记录CRITICAL级别日志"""
        if self.json_format:
            message = self._format_json_message("CRITICAL", message, **kwargs)
        self.logger.critical(message)


def get_logger(
    name: str = "reportgen", log_file: Optional[str] = None, level: str = "INFO"
) -> StructuredLogger:
    """
    获取日志记录器实例（工厂函数）

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别

    Returns:
        StructuredLogger实例
    """
    key = str(name)
    if key in _LOGGER_CACHE:
        inst = _LOGGER_CACHE[key]
        inst.configure(
            log_file=log_file, level=level, console_output=True, json_format=True
        )
        return inst

    inst = StructuredLogger(name=name, log_file=log_file, level=level)
    _LOGGER_CACHE[key] = inst
    return inst


_LOGGER_CACHE: dict[str, StructuredLogger] = {}
