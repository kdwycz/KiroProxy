"""全局状态管理"""
import time
from typing import Optional, List, Dict, Set
from pathlib import Path

from .logger import logger

from ..config import TOKEN_PATH
from ..credential import quota_manager, CredentialStatus
from .account import Account
from .persistence import load_accounts, save_accounts



class ProxyState:
    """全局状态管理"""
    
    def __init__(self):
        self.accounts: List[Account] = []
        self.session_locks: Dict[str, str] = {}
        self.session_timestamps: Dict[str, float] = {}
        self.start_time: float = time.time()
        self.current_port: int = 8080  # 当前运行端口
        self._load_accounts()
    
    def _load_accounts(self):
        """从配置文件加载账号"""
        saved = load_accounts()
        if saved:
            for acc_data in saved:
                # 验证 token 文件存在
                if Path(acc_data.get("token_path", "")).exists():
                    self.accounts.append(Account(
                        id=acc_data["id"],
                        name=acc_data["name"],
                        token_path=acc_data["token_path"],
                        enabled=acc_data.get("enabled", True),
                        machine_id=acc_data.get("machine_id"),
                        sqm_id=acc_data.get("sqm_id"),
                        dev_device_id=acc_data.get("dev_device_id"),
                    ))
            logger.info(f"从配置加载 {len(self.accounts)} 个账号")
        
        # 如果没有账号，尝试添加默认账号
        if not self.accounts and TOKEN_PATH.exists():
            self.accounts.append(Account(
                id="default",
                name="默认账号",
                token_path=str(TOKEN_PATH)
            ))
            self._save_accounts()
        
        # 迁移：为缺少 machine_id 的账号生成遥测 ID 并立即持久化
        needs_migration = any(not acc.machine_id for acc in self.accounts)
        if needs_migration and self.accounts:
            for acc in self.accounts:
                acc.get_machine_id()  # 触发 _init_telemetry_ids
            self._save_accounts()
            logger.info(f"已为 {sum(1 for a in self.accounts if a.machine_id)} 个账号生成遥测 ID")
    
    def _save_accounts(self):
        """保存账号到配置文件"""
        accounts_data = [
            {
                "id": acc.id,
                "name": acc.name,
                "token_path": acc.token_path,
                "enabled": acc.enabled,
                "machine_id": acc.get_machine_id(),
                "sqm_id": acc.sqm_id,
                "dev_device_id": acc.dev_device_id,
            }
            for acc in self.accounts
        ]
        save_accounts(accounts_data)
    
    def get_available_account(self, session_id: Optional[str] = None) -> Optional[Account]:
        """获取可用账号（支持会话粘性）"""
        from .stats import stats_manager
        quota_manager.cleanup_expired()
        
        # 会话粘性
        if session_id and session_id in self.session_locks:
            account_id = self.session_locks[session_id]
            ts = self.session_timestamps.get(session_id, 0)
            if time.time() - ts < 60:
                for acc in self.accounts:
                    if acc.id == account_id and acc.is_available():
                        self.session_timestamps[session_id] = time.time()
                        return acc
        
        available = [a for a in self.accounts if a.is_available()]
        if not available:
            return None
        
        account = min(available, key=lambda a: stats_manager.by_account[a.id].total_requests)
        
        if session_id:
            self.session_locks[session_id] = account.id
            self.session_timestamps[session_id] = time.time()
        
        return account
    
    def get_next_available_account(self, exclude_ids: Set[str] = None) -> Optional[Account]:
        """获取下一个可用账号（排除指定账号集合）"""
        from .stats import stats_manager
        if exclude_ids is None:
            exclude_ids = set()
        available = [a for a in self.accounts if a.is_available() and a.id not in exclude_ids]
        if not available:
            return None
        return min(available, key=lambda a: stats_manager.by_account[a.id].total_requests)
    
    def get_shortest_cooldown(self) -> tuple:
        """获取所有冷却中账号的最短剩余冷却时间
        
        Returns:
            (remaining_seconds, account) 或 (None, None)
        """
        remaining, cred_id = quota_manager.get_shortest_cooldown()
        if remaining is not None and cred_id is not None:
            for acc in self.accounts:
                if acc.id == cred_id:
                    return (remaining, acc)
        return (None, None)
    
    def mark_rate_limited(self, account_id: str, duration_seconds: int = 60):
        """标记账号限流"""
        for acc in self.accounts:
            if acc.id == account_id:
                acc.mark_quota_exceeded("Rate limited")
                break
    
    def mark_quota_exceeded(self, account_id: str, reason: str = "Quota exceeded"):
        """标记账号配额超限"""
        for acc in self.accounts:
            if acc.id == account_id:
                acc.mark_quota_exceeded(reason)
                break
    
    async def refresh_account_token(self, account_id: str) -> tuple:
        """刷新指定账号的 token"""
        for acc in self.accounts:
            if acc.id == account_id:
                return await acc.refresh_token()
        return False, "账号不存在"
    
    async def refresh_expiring_tokens(self) -> List[dict]:
        """刷新所有即将过期的 token"""
        results = []
        for acc in self.accounts:
            if acc.enabled and acc.is_token_expiring_soon(10):
                success, msg = await acc.refresh_token()
                results.append({
                    "account_id": acc.id,
                    "success": success,
                    "message": msg
                })
        return results
    
    def get_stats(self) -> dict:
        """获取统计信息（代理 StatsManager 数据）"""
        from .stats import stats_manager
        uptime = time.time() - self.start_time
        return {
            "uptime_seconds": int(uptime),
            "total_requests": stats_manager.total_requests,
            "total_errors": stats_manager.total_errors,
            "error_rate": f"{(stats_manager.total_errors / max(1, stats_manager.total_requests) * 100):.1f}%",
            "accounts_total": len(self.accounts),
            "accounts_available": len([a for a in self.accounts if a.is_available()]),
            "accounts_cooldown": len([a for a in self.accounts if a.status == CredentialStatus.COOLDOWN]),
        }
    
    def get_accounts_status(self) -> List[dict]:
        """获取所有账号状态"""
        return [acc.get_status_info() for acc in self.accounts]


# 全局状态实例
state = ProxyState()
