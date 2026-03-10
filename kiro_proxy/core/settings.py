"""配置文件管理 - settings.toml

配置文件路径: <project>/data/settings.toml
首次启动自动创建默认配置。
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# 项目根目录 (kiro_proxy/core/settings.py -> kiro_proxy/core -> kiro_proxy -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "data"
SETTINGS_FILE = CONFIG_DIR / "settings.toml"

DEFAULT_SETTINGS_TOML = """\
[server]
port = 8080

[proxy]
quota_cooldown_seconds = 300
web_search_enabled = false
request_timeout = 300
max_retries = 2
max_flows = 500

[sentry]
dsn = ""
environment = "production"
traces_sample_rate = 0.1

[logging]
level = "INFO"
dir = "data/logs"
rotation = "00:00"
retention = "30 days"
api_log_enabled = true
api_log_max_body_chars = 50000
"""


@dataclass
class ServerSettings:
    port: int = 8080


@dataclass
class ProxySettings:
    quota_cooldown_seconds: int = 300
    web_search_enabled: bool = False
    request_timeout: int = 300
    max_retries: int = 2
    max_flows: int = 500


@dataclass
class SentrySettings:
    dsn: str = ""
    environment: str = "production"
    traces_sample_rate: float = 0.1


@dataclass
class LoggingSettings:
    level: str = "INFO"
    dir: str = "data/logs"
    rotation: str = "00:00"
    retention: str = "30 days"
    api_log_enabled: bool = True
    api_log_max_body_chars: int = 50000

    @property
    def log_dir(self) -> Path:
        p = Path(self.dir)
        if p.is_absolute():
            return p
        # 相对路径基于项目根目录
        return PROJECT_ROOT / p


@dataclass
class Settings:
    server: ServerSettings = field(default_factory=ServerSettings)
    proxy: ProxySettings = field(default_factory=ProxySettings)
    sentry: SentrySettings = field(default_factory=SentrySettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


def _ensure_settings_file():
    """确保配置文件存在，不存在则创建默认配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(DEFAULT_SETTINGS_TOML, encoding="utf-8")


def load_settings(path: Optional[Path] = None) -> Settings:
    """加载配置文件

    Args:
        path: 配置文件路径，默认 <project>/data/settings.toml

    Returns:
        Settings 实例
    """
    settings_path = path or SETTINGS_FILE
    settings = Settings()

    if not settings_path.exists():
        _ensure_settings_file()
        if not settings_path.exists():
            return settings

    try:
        with open(settings_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        from .logger import logger
        logger.warning(f"加载配置文件失败: {e}，使用默认配置")
        return settings

    # server
    if "server" in data:
        s = data["server"]
        settings.server = ServerSettings(
            port=s.get("port", 8080),
        )

    # proxy
    if "proxy" in data:
        p = data["proxy"]
        settings.proxy = ProxySettings(
            quota_cooldown_seconds=p.get("quota_cooldown_seconds", 300),
            web_search_enabled=p.get("web_search_enabled", False),
            request_timeout=p.get("request_timeout", 300),
            max_retries=p.get("max_retries", 2),
            max_flows=p.get("max_flows", 500),
        )

    # sentry
    if "sentry" in data:
        s = data["sentry"]
        settings.sentry = SentrySettings(
            dsn=s.get("dsn", ""),
            environment=s.get("environment", "production"),
            traces_sample_rate=s.get("traces_sample_rate", 0.1),
        )

    # logging
    if "logging" in data:
        lg = data["logging"]
        settings.logging = LoggingSettings(
            level=lg.get("level", "INFO"),
            dir=lg.get("dir", "data/logs"),
            rotation=lg.get("rotation", "00:00"),
            retention=lg.get("retention", "30 days"),
            api_log_enabled=lg.get("api_log_enabled", True),
            api_log_max_body_chars=lg.get("api_log_max_body_chars", 50000),
        )

    return settings


# 全局设置实例（延迟初始化）
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局设置实例"""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置文件"""
    global _settings
    _settings = load_settings()
    return _settings
