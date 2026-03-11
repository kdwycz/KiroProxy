"""配额管理"""
import time
from dataclasses import dataclass
from typing import Dict, Optional, List


# 指数退避序列（秒）
BACKOFF_SEQUENCE: List[int] = [5, 10, 30, 60, 120, 300]


@dataclass
class QuotaRecord:
    """配额超限记录"""
    credential_id: str
    exceeded_at: float
    cooldown_until: float
    reason: str
    backoff_level: int = 0
    last_429_at: float = 0.0
    total_429_count: int = 0


class QuotaManager:
    """配额管理器
    
    管理凭证的配额超限状态：
    - 标记凭证为配额超限（指数退避冷却时间）
    - 检查凭证是否可用
    - 自动清理过期的冷却状态
    - 成功请求后重置退避级别
    """
    
    QUOTA_KEYWORDS = [
        "rate limit", "quota", "too many requests", "throttl",
        "capacity", "overloaded", "try again later"
    ]
    
    QUOTA_STATUS_CODES = {429, 503, 529}
    
    def __init__(self):
        self.exceeded_records: Dict[str, QuotaRecord] = {}
    
    @property
    def cooldown_seconds(self) -> int:
        """最大冷却时间（用于展示）"""
        return BACKOFF_SEQUENCE[-1]
    
    def is_quota_exceeded_error(self, status_code: Optional[int], error_message: str) -> bool:
        """检查是否为配额超限错误"""
        if status_code and status_code in self.QUOTA_STATUS_CODES:
            return True
        
        error_lower = error_message.lower()
        return any(kw in error_lower for kw in self.QUOTA_KEYWORDS)
    
    def mark_exceeded(self, credential_id: str, reason: str, cooldown_seconds: int = None) -> QuotaRecord:
        """标记凭证为配额超限（使用指数退避）
        
        如果提供了 cooldown_seconds，使用指定值；
        否则根据当前退避级别从 BACKOFF_SEQUENCE 中选择冷却时间。
        """
        now = time.time()
        
        # 获取或创建记录
        existing = self.exceeded_records.get(credential_id)
        
        if existing:
            # 递增退避级别
            new_level = min(existing.backoff_level + 1, len(BACKOFF_SEQUENCE) - 1)
            total_429 = existing.total_429_count + 1
        else:
            new_level = 0
            total_429 = 1
        
        # 确定冷却时间
        if cooldown_seconds is not None:
            cooldown = cooldown_seconds
        else:
            cooldown = BACKOFF_SEQUENCE[new_level]
        
        record = QuotaRecord(
            credential_id=credential_id,
            exceeded_at=now,
            cooldown_until=now + cooldown,
            reason=reason,
            backoff_level=new_level,
            last_429_at=now,
            total_429_count=total_429,
        )
        self.exceeded_records[credential_id] = record
        return record
    
    def reset_backoff(self, credential_id: str):
        """重置退避级别（成功请求时调用）
        
        保留 total_429_count 和 last_429_at 用于统计展示，
        但清除冷却记录和重置退避级别。
        """
        record = self.exceeded_records.get(credential_id)
        if record:
            # 保留统计信息但清除冷却
            record.backoff_level = 0
            record.cooldown_until = 0  # 立刻可用
    
    def is_available(self, credential_id: str) -> bool:
        """检查凭证是否可用"""
        record = self.exceeded_records.get(credential_id)
        if not record:
            return True
        
        if time.time() >= record.cooldown_until:
            # 冷却过期，不删除记录（保留统计信息），但标记为可用
            return True
        
        return False
    
    def get_cooldown_remaining(self, credential_id: str) -> Optional[int]:
        """获取剩余冷却时间（秒）"""
        record = self.exceeded_records.get(credential_id)
        if not record:
            return None
        
        remaining = record.cooldown_until - time.time()
        if remaining <= 0:
            return 0
        return int(remaining)
    
    def get_rate_limit_info(self, credential_id: str) -> dict:
        """获取限速相关信息（用于 API 展示）"""
        record = self.exceeded_records.get(credential_id)
        cooldown_remaining = self.get_cooldown_remaining(credential_id)
        
        if not record:
            return {
                "is_cooldown": False,
                "cooldown_remaining": 0,
                "backoff_level": 0,
                "last_429_at": None,
                "total_429_count": 0,
            }
        
        return {
            "is_cooldown": cooldown_remaining is not None and cooldown_remaining > 0,
            "cooldown_remaining": cooldown_remaining or 0,
            "backoff_level": record.backoff_level,
            "last_429_at": record.last_429_at,
            "total_429_count": record.total_429_count,
        }
    
    def get_shortest_cooldown(self) -> tuple:
        """获取所有冷却中账号的最短剩余冷却时间
        
        Returns:
            (remaining_seconds, credential_id) 或 (None, None) 如果没有冷却中的账号
        """
        now = time.time()
        shortest = None
        shortest_id = None
        
        for cred_id, record in self.exceeded_records.items():
            remaining = record.cooldown_until - now
            if remaining > 0:
                if shortest is None or remaining < shortest:
                    shortest = remaining
                    shortest_id = cred_id
        
        return (shortest, shortest_id)
    
    def cleanup_expired(self) -> int:
        """清理过期的冷却记录（退避级别已重置且冷却已过期的）"""
        now = time.time()
        expired = [
            k for k, v in self.exceeded_records.items()
            if now >= v.cooldown_until and v.backoff_level == 0
        ]
        for k in expired:
            del self.exceeded_records[k]
        return len(expired)
    
    def restore(self, credential_id: str) -> bool:
        """手动恢复凭证"""
        if credential_id in self.exceeded_records:
            del self.exceeded_records[credential_id]
            return True
        return False


# 全局实例
quota_manager = QuotaManager()
