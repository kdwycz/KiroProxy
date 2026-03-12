"""请求统计 — 单一数据源

StatsManager 是唯一的数字统计数据源。
- 全局 total_requests / total_errors 计数器
- 按账号、模型、小时粒度聚合
- 按天分区 daily: Dict[str, DailyStats]
- 持久化到 data/stats.json（total + daily，清理 30 天前）
- 每 60 秒 + 进程退出时自动保存
"""
from __future__ import annotations

import asyncio
import atexit
import json
import signal
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


@dataclass
class AccountStats:
    """账号统计"""
    total_requests: int = 0
    total_errors: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    last_request_time: float = 0

    def record(self, success: bool, tokens_in: int = 0, tokens_out: int = 0):
        self.total_requests += 1
        if not success:
            self.total_errors += 1
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.last_request_time = time.time()

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0
        return self.total_errors / self.total_requests

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "last_request_time": self.last_request_time,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AccountStats":
        return cls(
            total_requests=d.get("total_requests", 0),
            total_errors=d.get("total_errors", 0),
            total_tokens_in=d.get("total_tokens_in", 0),
            total_tokens_out=d.get("total_tokens_out", 0),
            last_request_time=d.get("last_request_time", 0),
        )


@dataclass
class ModelStats:
    """模型统计"""
    total_requests: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0

    def record(self, success: bool, latency_ms: float):
        self.total_requests += 1
        if not success:
            self.total_errors += 1
        self.total_latency_ms += latency_ms

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0
        return self.total_latency_ms / self.total_requests

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "total_latency_ms": self.total_latency_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModelStats":
        return cls(
            total_requests=d.get("total_requests", 0),
            total_errors=d.get("total_errors", 0),
            total_latency_ms=d.get("total_latency_ms", 0),
        )


@dataclass
class DailyStats:
    """按天统计"""
    requests: int = 0
    errors: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def record(self, success: bool, tokens_in: int = 0, tokens_out: int = 0):
        self.requests += 1
        if not success:
            self.errors += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def to_dict(self) -> dict:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DailyStats":
        return cls(
            requests=d.get("requests", 0),
            errors=d.get("errors", 0),
            tokens_in=d.get("tokens_in", 0),
            tokens_out=d.get("tokens_out", 0),
        )


class StatsManager:
    """统计管理器 — 唯一统计数据源"""

    # 持久化文件相对路径（相对于项目根目录）
    STATS_FILE = "data/stats.json"
    # 保留天数
    RETENTION_DAYS = 30
    # 自动保存间隔（秒）
    AUTO_SAVE_INTERVAL = 60

    def __init__(self):
        # 全局累计计数器
        self.total_requests: int = 0
        self.total_errors: int = 0

        # 分维度
        self.by_account: Dict[str, AccountStats] = defaultdict(AccountStats)
        self.by_model: Dict[str, ModelStats] = defaultdict(ModelStats)
        self.hourly_requests: Dict[int, int] = defaultdict(int)  # hour -> count

        # 按天分区
        self.daily: Dict[str, DailyStats] = {}

        # 内部状态
        self._stats_path: Optional[Path] = None
        self._auto_save_task: Optional[asyncio.Task] = None
        self._dirty: bool = False

    # ── 初始化 ──────────────────────────────────────────

    def init(self, project_root: Path | str | None = None):
        """初始化：设置路径、加载持久化数据、注册退出钩子"""
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent
        project_root = Path(project_root)
        self._stats_path = project_root / self.STATS_FILE
        self._stats_path.parent.mkdir(parents=True, exist_ok=True)

        self.load()
        atexit.register(self._save_sync)

    # ── 记录请求 ────────────────────────────────────────

    def record_request(
        self,
        account_id: str,
        model: str,
        success: bool,
        latency_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ):
        """记录一次请求（所有 handler 统一调用此方法）"""
        # 全局计数器
        self.total_requests += 1
        if not success:
            self.total_errors += 1

        # 按账号
        self.by_account[account_id].record(success, tokens_in, tokens_out)

        # 按模型
        self.by_model[model].record(success, latency_ms)

        # 按小时
        hour = int(time.time() // 3600)
        self.hourly_requests[hour] += 1
        self._cleanup_hourly()

        # 按天
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.daily:
            self.daily[today] = DailyStats()
        self.daily[today].record(success, tokens_in, tokens_out)

        self._dirty = True

    # ── 查询 ────────────────────────────────────────────

    def get_account_stats(self, account_id: str) -> dict:
        """获取账号统计"""
        stats = self.by_account.get(account_id, AccountStats())
        return {
            "total_requests": stats.total_requests,
            "total_errors": stats.total_errors,
            "error_rate": f"{stats.error_rate * 100:.1f}%",
            "total_tokens_in": stats.total_tokens_in,
            "total_tokens_out": stats.total_tokens_out,
            "last_request": stats.last_request_time,
        }

    def get_model_stats(self, model: str) -> dict:
        """获取模型统计"""
        stats = self.by_model.get(model, ModelStats())
        return {
            "total_requests": stats.total_requests,
            "total_errors": stats.total_errors,
            "avg_latency_ms": round(stats.avg_latency_ms, 2),
        }

    def get_all_stats(self) -> dict:
        """获取所有统计（供 /api/stats 使用）"""
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": f"{(self.total_errors / max(1, self.total_requests) * 100):.1f}%",
            "by_account": {
                acc_id: self.get_account_stats(acc_id) for acc_id in self.by_account
            },
            "by_model": {
                model: self.get_model_stats(model) for model in self.by_model
            },
            "hourly_requests": dict(self.hourly_requests),
            "requests_last_24h": sum(self.hourly_requests.values()),
            "daily": {
                day: ds.to_dict() for day, ds in sorted(self.daily.items())
            },
        }

    # ── 持久化 ──────────────────────────────────────────

    def save(self):
        """写入 data/stats.json（total + daily，清理 30 天前）"""
        if self._stats_path is None:
            return

        self._cleanup_daily()

        data = {
            "total": {
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
            },
            "by_account": {
                acc_id: s.to_dict() for acc_id, s in self.by_account.items()
            },
            "by_model": {
                model: s.to_dict() for model, s in self.by_model.items()
            },
            "daily": {
                day: ds.to_dict() for day, ds in self.daily.items()
            },
            "saved_at": datetime.now().isoformat(),
        }

        try:
            tmp = self._stats_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._stats_path)
            self._dirty = False
        except Exception as e:
            from .logger import logger
            logger.warning(f"统计数据保存失败: {e}")

    def load(self):
        """启动时加载历史数据"""
        if self._stats_path is None or not self._stats_path.exists():
            return

        try:
            data = json.loads(self._stats_path.read_text(encoding="utf-8"))
        except Exception as e:
            from .logger import logger
            logger.warning(f"统计数据加载失败: {e}")
            return

        # 全局
        total = data.get("total", {})
        self.total_requests = total.get("total_requests", 0)
        self.total_errors = total.get("total_errors", 0)

        # 按账号
        for acc_id, acc_d in data.get("by_account", {}).items():
            self.by_account[acc_id] = AccountStats.from_dict(acc_d)

        # 按模型
        for model, model_d in data.get("by_model", {}).items():
            self.by_model[model] = ModelStats.from_dict(model_d)

        # 按天
        for day, day_d in data.get("daily", {}).items():
            self.daily[day] = DailyStats.from_dict(day_d)

        self._cleanup_daily()
        from .logger import logger
        logger.info(f"统计数据已加载: {self.total_requests} 请求, {len(self.daily)} 天记录")

    # ── 自动保存 ────────────────────────────────────────

    async def start_auto_save(self):
        """启动异步自动保存循环（每 60 秒）"""
        if self._auto_save_task is not None:
            return

        async def _loop():
            while True:
                await asyncio.sleep(self.AUTO_SAVE_INTERVAL)
                if self._dirty:
                    self.save()

        self._auto_save_task = asyncio.create_task(_loop())

    def stop_auto_save(self):
        """停止自动保存"""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None

    def _save_sync(self):
        """同步保存（atexit 钩子用）"""
        if self._dirty:
            self.save()

    # ── 内部 ────────────────────────────────────────────

    def _cleanup_hourly(self):
        """清理超过 24 小时的数据"""
        current_hour = int(time.time() // 3600)
        cutoff = current_hour - 24
        self.hourly_requests = defaultdict(
            int, {h: c for h, c in self.hourly_requests.items() if h > cutoff}
        )

    def _cleanup_daily(self):
        """清理超过 30 天的 daily 数据"""
        cutoff = (datetime.now() - timedelta(days=self.RETENTION_DAYS)).strftime("%Y-%m-%d")
        self.daily = {day: ds for day, ds in self.daily.items() if day >= cutoff}


# 全局统计实例
stats_manager = StatsManager()
