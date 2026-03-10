"""Loguru 日志模块

提供统一的日志接口，替代 print()。
配置 3 个 sink：stderr（彩色）、文件（按天轮转）、Sentry（ERROR+）。
"""
import sys
from loguru import logger as _loguru_logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import Settings

# 移除 loguru 默认的 stderr handler
_loguru_logger.remove()

# 全局 logger 实例
logger = _loguru_logger

_initialized = False


def setup_logging(settings: "Settings"):
    """初始化日志系统

    Args:
        settings: 配置实例
    """
    global _initialized
    if _initialized:
        return

    log_config = settings.logging
    log_dir = log_config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1. stderr — 彩色控制台输出
    logger.add(
        sys.stderr,
        level=log_config.level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # 2. 文件 — 按天轮转
    logger.add(
        str(log_dir / "kiro-proxy.log"),
        level=log_config.level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} - {message}",
        rotation=log_config.rotation,
        retention=log_config.retention,
        encoding="utf-8",
        enqueue=True,  # 线程安全
    )

    # 3. Sentry — ERROR+ 级别
    sentry_dsn = settings.sentry.dsn
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration

            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=settings.sentry.environment,
                traces_sample_rate=settings.sentry.traces_sample_rate,
                integrations=[
                    FastApiIntegration(),
                    StarletteIntegration(),
                ],
            )

            # 添加 Sentry sink（捕获 ERROR+ 日志）
            def _sentry_sink(message):
                record = message.record
                level = record["level"].name
                if level in ("ERROR", "CRITICAL"):
                    sentry_sdk.capture_message(
                        str(record["message"]),
                        level=level.lower(),
                    )
                if record["exception"] is not None:
                    sentry_sdk.capture_exception(record["exception"].value)

            logger.add(
                _sentry_sink,
                level="ERROR",
                format="{message}",
            )

            logger.info(f"Sentry 已初始化: environment={settings.sentry.environment}")
        except ImportError:
            logger.warning("sentry-sdk 未安装，Sentry 集成已跳过")
        except Exception as e:
            logger.warning(f"Sentry 初始化失败: {e}")

    # 确保 flows 日志目录存在
    if log_config.api_log_enabled:
        flows_dir = log_dir / "flows"
        flows_dir.mkdir(parents=True, exist_ok=True)

    _initialized = True
    logger.info(f"日志系统已初始化: level={log_config.level}, dir={log_dir}")
