"""请求重试机制"""
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Any, Optional, Set
from functools import wraps

from .logger import logger

# 可重试的状态码
RETRYABLE_STATUS_CODES: Set[int] = {
    408,  # Request Timeout
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

# 不可重试的状态码（直接返回错误）
NON_RETRYABLE_STATUS_CODES: Set[int] = {
    400,  # Bad Request
    401,  # Unauthorized
    403,  # Forbidden
    404,  # Not Found
    422,  # Unprocessable Entity
}


def is_retryable_error(status_code: Optional[int], error: Optional[Exception] = None) -> bool:
    """判断是否为可重试的错误"""
    # 网络错误可重试
    if error:
        error_name = type(error).__name__.lower()
        if any(kw in error_name for kw in ['timeout', 'connect', 'network', 'reset']):
            return True
    
    # 特定状态码可重试
    if status_code and status_code in RETRYABLE_STATUS_CODES:
        return True
    
    return False


def is_non_retryable_error(status_code: Optional[int]) -> bool:
    """判断是否为不可重试的错误"""
    return status_code in NON_RETRYABLE_STATUS_CODES if status_code else False


async def retry_async(
    func: Callable,
    max_retries: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Any:
    """
    异步重试装饰器
    
    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        on_retry: 重试时的回调函数
    """
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_error = e
            
            # 检查是否可重试
            status_code = getattr(e, 'status_code', None)
            if is_non_retryable_error(status_code):
                raise
            
            if attempt < max_retries and is_retryable_error(status_code, e):
                # 指数退避
                delay = min(base_delay * (2 ** attempt), max_delay)
                
                if on_retry:
                    on_retry(attempt + 1, e)
                else:
                    logger.info(f"第 {attempt + 1} 次重试，延迟 {delay:.1f}s，错误: {type(e).__name__}")
                
                await asyncio.sleep(delay)
            else:
                raise
    
    raise last_error


class RetryableRequest:
    """可重试的请求上下文"""
    
    def __init__(self, max_retries: int = 2, base_delay: float = 0.5):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.attempt = 0
        self.last_error = None
    
    def should_retry(self, status_code: Optional[int] = None, error: Optional[Exception] = None) -> bool:
        """判断是否应该重试"""
        self.attempt += 1
        self.last_error = error
        
        if self.attempt > self.max_retries:
            return False
        
        if is_non_retryable_error(status_code):
            return False
        
        return is_retryable_error(status_code, error)
    
    async def wait(self):
        """等待重试延迟"""
        delay = min(self.base_delay * (2 ** (self.attempt - 1)), 5.0)
        logger.info(f"第 {self.attempt} 次重试，延迟 {delay:.1f}s")
        await asyncio.sleep(delay)


@dataclass
class RetryContext:
    """429 重试上下文，在整个请求生命周期中共享"""
    tried_accounts: Set[str] = field(default_factory=set)
    quick_retry_done: bool = False


async def handle_429(current_account, headers: dict, ctx: RetryContext, handler_name: str = ""):
    """两阶段 429 重试处理
    
    Phase 1: sleep 2s，同账号重试（覆盖大部分瞬时限速）
    Phase 2: 标记冷却（指数退避），换号或等最短冷却
    
    Returns:
        (account, should_continue)
        - should_continue=True: 调用方应 continue，account 是下次要用的账号
        - should_continue=False: 无法恢复，调用方应返回 429 错误
    """
    from . import state as state_module
    state = state_module.state
    tag = f"({handler_name})" if handler_name else ""
    
    # === 第一阶段：快速重试同账号 ===
    if not ctx.quick_retry_done:
        ctx.quick_retry_done = True
        logger.info(f"429 快速重试{tag}: 账号 {current_account.id}，sleep 2s 后同账号重试")
        await asyncio.sleep(2)
        return current_account, True
    
    # === 第二阶段：冷却 + 换号 ===
    current_account.mark_quota_exceeded(f"Rate limited {tag}".strip())
    ctx.tried_accounts.add(current_account.id)
    
    # 尝试切换到未试过的可用账号
    next_account = state.get_next_available_account(exclude_ids=ctx.tried_accounts)
    if next_account:
        logger.info(f"配额超限，切换账号: {current_account.id} -> {next_account.id}")
        headers["Authorization"] = f"Bearer {next_account.get_token()}"
        ctx.quick_retry_done = False  # 新账号重置快速重试
        return next_account, True

    # 无可用账号 - 检查最短冷却时间
    remaining, cooldown_account = state.get_shortest_cooldown()
    if remaining is not None and remaining <= 5:
        logger.info(f"所有账号限速中，等待 {remaining:.1f}s 后重试 {cooldown_account.id}")
        await asyncio.sleep(remaining + 0.5)
        headers["Authorization"] = f"Bearer {cooldown_account.get_token()}"
        return cooldown_account, True

    # 无法恢复
    return current_account, False
