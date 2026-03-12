"""Flow Monitor - LLM 流量监控

记录完整的请求/响应数据，支持查询、过滤。
支持 JSONL 文件持久化。
完成/失败时自动同步 StatsManager 统计。
"""
import json
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from collections import deque
from enum import Enum

from .logger import logger


class FlowState(str, Enum):
    """Flow 状态"""
    PENDING = "pending"      # 等待响应
    STREAMING = "streaming"  # 流式传输中
    COMPLETED = "completed"  # 完成
    ERROR = "error"          # 错误


@dataclass
class Message:
    """消息"""
    role: str  # user/assistant/system/tool
    content: Any  # str 或 list
    name: Optional[str] = None  # tool name
    tool_call_id: Optional[str] = None


@dataclass
class TokenUsage:
    """Token 使用量"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class FlowRequest:
    """请求数据"""
    method: str
    path: str
    headers: Dict[str, str]
    body: Dict[str, Any]
    
    # 解析后的字段
    model: str = ""
    messages: List[Message] = field(default_factory=list)
    system: str = ""
    tools: List[Dict] = field(default_factory=list)
    stream: bool = False
    max_tokens: int = 0
    temperature: float = 1.0


@dataclass
class FlowResponse:
    """响应数据"""
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None
    
    # 解析后的字段
    content: str = ""
    tool_calls: List[Dict] = field(default_factory=list)
    stop_reason: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    
    # 流式响应
    chunks: List[str] = field(default_factory=list)
    chunk_count: int = 0


@dataclass
class FlowError:
    """错误信息"""
    type: str  # rate_limit_error, api_error, etc.
    message: str
    status_code: int = 0
    raw: str = ""


@dataclass 
class FlowTiming:
    """时间信息"""
    created_at: float = 0
    first_byte_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    @property
    def ttfb_ms(self) -> Optional[float]:
        """Time to first byte"""
        if self.first_byte_at and self.created_at:
            return (self.first_byte_at - self.created_at) * 1000
        return None
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Total duration"""
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at) * 1000
        return None


@dataclass
class LLMFlow:
    """完整的 LLM 请求流"""
    id: str
    state: FlowState
    
    # 路由信息
    protocol: str  # anthropic, openai, gemini
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    
    # 请求/响应
    request: Optional[FlowRequest] = None
    response: Optional[FlowResponse] = None
    error: Optional[FlowError] = None
    
    # 时间
    timing: FlowTiming = field(default_factory=FlowTiming)
    
    # 重试信息
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        """转换为字典（列表展示用）"""
        d = {
            "id": self.id,
            "state": self.state.value,
            "protocol": self.protocol,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "timing": {
                "created_at": self.timing.created_at,
                "first_byte_at": self.timing.first_byte_at,
                "completed_at": self.timing.completed_at,
                "ttfb_ms": self.timing.ttfb_ms,
                "duration_ms": self.timing.duration_ms,
            },
            "retry_count": self.retry_count,
        }
        
        if self.request:
            d["request"] = {
                "method": self.request.method,
                "path": self.request.path,
                "model": self.request.model,
                "stream": self.request.stream,
                "message_count": len(self.request.messages),
                "has_tools": bool(self.request.tools),
                "has_system": bool(self.request.system),
            }
        
        if self.response:
            d["response"] = {
                "status_code": self.response.status_code,
                "content_length": len(self.response.content),
                "has_tool_calls": bool(self.response.tool_calls),
                "stop_reason": self.response.stop_reason,
                "chunk_count": self.response.chunk_count,
                "usage": asdict(self.response.usage),
            }
        
        if self.error:
            d["error"] = asdict(self.error)
        
        return d
    
    def to_full_dict(self) -> dict:
        """转换为完整字典（包含请求/响应体）"""
        d = self.to_dict()
        
        if self.request:
            d["request"]["headers"] = self.request.headers
            d["request"]["body"] = self.request.body
            d["request"]["messages"] = [asdict(m) if hasattr(m, '__dataclass_fields__') else m for m in self.request.messages]
            d["request"]["system"] = self.request.system
            d["request"]["tools"] = self.request.tools
        
        if self.response:
            d["response"]["headers"] = self.response.headers
            d["response"]["body"] = self.response.body
            d["response"]["content"] = self.response.content
            d["response"]["tool_calls"] = self.response.tool_calls
            d["response"]["chunks"] = self.response.chunks[-10:]  # 只保留最后10个chunk
        
        return d


class FlowStore:
    """Flow 存储"""
    
    def __init__(self, max_flows: int = 500):
        self.flows: deque[LLMFlow] = deque(maxlen=max_flows)
        self.flow_map: Dict[str, LLMFlow] = {}
        self.max_flows = max_flows
        
        # 统计
        self.total_flows = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
    
    def add(self, flow: LLMFlow):
        """添加 Flow"""
        # 如果队列满了，移除最旧的
        if len(self.flows) >= self.max_flows:
            old = self.flows[0]
            if old.id in self.flow_map:
                del self.flow_map[old.id]
        
        self.flows.append(flow)
        self.flow_map[flow.id] = flow
        self.total_flows += 1
    
    def get(self, flow_id: str) -> Optional[LLMFlow]:
        """获取 Flow"""
        return self.flow_map.get(flow_id)
    
    def update(self, flow_id: str, **kwargs):
        """更新 Flow"""
        flow = self.flow_map.get(flow_id)
        if flow:
            for k, v in kwargs.items():
                if hasattr(flow, k):
                    setattr(flow, k, v)
    
    def query(
        self,
        protocol: Optional[str] = None,
        model: Optional[str] = None,
        account_id: Optional[str] = None,
        state: Optional[FlowState] = None,
        has_error: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LLMFlow]:
        """查询 Flows"""
        results = []
        
        for flow in reversed(self.flows):
            # 过滤条件
            if protocol and flow.protocol != protocol:
                continue
            if model and flow.request and flow.request.model != model:
                continue
            if account_id and flow.account_id != account_id:
                continue
            if state and flow.state != state:
                continue
            if has_error is not None:
                if has_error and not flow.error:
                    continue
                if not has_error and flow.error:
                    continue
            if search:
                # 简单搜索：在内容中查找
                found = False
                if flow.request and search.lower() in json.dumps(flow.request.body).lower():
                    found = True
                if flow.response and search.lower() in flow.response.content.lower():
                    found = True
                if not found:
                    continue
            
            results.append(flow)
        
        return results[offset:offset + limit]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        completed = [f for f in self.flows if f.state == FlowState.COMPLETED]
        errors = [f for f in self.flows if f.state == FlowState.ERROR]
        
        # 按模型统计
        model_stats = {}
        for f in self.flows:
            if f.request:
                model = f.request.model or "unknown"
                if model not in model_stats:
                    model_stats[model] = {"count": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0}
                model_stats[model]["count"] += 1
                if f.error:
                    model_stats[model]["errors"] += 1
                if f.response and f.response.usage:
                    model_stats[model]["tokens_in"] += f.response.usage.input_tokens
                    model_stats[model]["tokens_out"] += f.response.usage.output_tokens
        
        # 计算平均延迟
        durations = [f.timing.duration_ms for f in completed if f.timing.duration_ms]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "total_flows": self.total_flows,
            "active_flows": len(self.flows),
            "completed": len(completed),
            "errors": len(errors),
            "error_rate": f"{len(errors) / max(1, len(self.flows)) * 100:.1f}%",
            "avg_duration_ms": round(avg_duration, 2),
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "by_model": model_stats,
        }


class FlowMonitor:
    """Flow 监控器 — 唯一的请求记录入口
    
    Handler 只需调用 create_flow / complete_flow / fail_flow。
    完成/失败时自动同步到 StatsManager。
    """
    
    def __init__(self, max_flows: int = 500):
        self.store = FlowStore(max_flows=max_flows)
    
    def create_flow(
        self,
        protocol: str,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        account_id: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> str:
        """创建新的 Flow"""
        flow_id = uuid.uuid4().hex[:12]
        
        # 解析请求
        request = FlowRequest(
            method=method,
            path=path,
            headers={k: v for k, v in headers.items() if k.lower() not in ["authorization"]},
            body=body,
            model=body.get("model", ""),
            stream=body.get("stream", False),
            system=body.get("system", ""),
            tools=body.get("tools", []),
            max_tokens=body.get("max_tokens", 0),
            temperature=body.get("temperature", 1.0),
        )
        
        # 解析消息
        messages = body.get("messages", [])
        for msg in messages:
            request.messages.append(Message(
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                name=msg.get("name"),
                tool_call_id=msg.get("tool_call_id"),
            ))
        
        flow = LLMFlow(
            id=flow_id,
            state=FlowState.PENDING,
            protocol=protocol,
            account_id=account_id,
            account_name=account_name,
            request=request,
            timing=FlowTiming(created_at=time.time()),
        )
        
        self.store.add(flow)
        return flow_id
    
    def start_streaming(self, flow_id: str):
        """标记开始流式传输"""
        flow = self.store.get(flow_id)
        if flow:
            flow.state = FlowState.STREAMING
            flow.timing.first_byte_at = time.time()
            if not flow.response:
                flow.response = FlowResponse(status_code=200)
    
    def add_chunk(self, flow_id: str, chunk: str):
        """添加流式响应块"""
        flow = self.store.get(flow_id)
        if flow and flow.response:
            flow.response.chunks.append(chunk)
            flow.response.chunk_count += 1
            flow.response.content += chunk
    
    def complete_flow(
        self,
        flow_id: str,
        status_code: int,
        content: str = "",
        tool_calls: List[Dict] = None,
        stop_reason: str = "",
        usage: Optional[TokenUsage] = None,
        headers: Dict[str, str] = None,
    ):
        """完成 Flow，并自动同步到 StatsManager"""
        flow = self.store.get(flow_id)
        if not flow:
            return
        
        flow.state = FlowState.COMPLETED
        flow.timing.completed_at = time.time()
        
        if not flow.response:
            flow.response = FlowResponse(status_code=status_code)
        
        flow.response.status_code = status_code
        flow.response.content = content or flow.response.content
        flow.response.tool_calls = tool_calls or []
        flow.response.stop_reason = stop_reason
        flow.response.headers = headers or {}
        
        tokens_in = 0
        tokens_out = 0
        if usage:
            flow.response.usage = usage
            tokens_in = usage.input_tokens
            tokens_out = usage.output_tokens
            self.store.total_tokens_in += tokens_in
            self.store.total_tokens_out += tokens_out

        # ── 自动同步到 StatsManager ──
        self._sync_stats(flow, success=True, tokens_in=tokens_in, tokens_out=tokens_out)

        # 持久化到 JSONL
        self._write_flow_jsonl(flow)
    
    def fail_flow(self, flow_id: str, error_type: str, message: str, status_code: int = 0, raw: str = ""):
        """标记 Flow 失败，并自动同步到 StatsManager"""
        flow = self.store.get(flow_id)
        if not flow:
            return
        
        flow.state = FlowState.ERROR
        flow.timing.completed_at = time.time()
        flow.error = FlowError(
            type=error_type,
            message=message,
            status_code=status_code,
            raw=raw[:1000],  # 限制长度
        )

        # ── 自动同步到 StatsManager ──
        self._sync_stats(flow, success=False)

        # 持久化到 JSONL
        self._write_flow_jsonl(flow)
    
    def _sync_stats(self, flow: LLMFlow, success: bool, tokens_in: int = 0, tokens_out: int = 0):
        """内部：同步到 StatsManager"""
        from .stats import stats_manager
        
        account_id = flow.account_id or "unknown"
        model = flow.request.model if flow.request else "unknown"
        latency_ms = flow.timing.duration_ms or 0
        
        stats_manager.record_request(
            account_id=account_id,
            model=model,
            success=success,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def get_flow(self, flow_id: str) -> Optional[LLMFlow]:
        """获取 Flow"""
        return self.store.get(flow_id)
    
    def query(self, **kwargs) -> List[LLMFlow]:
        """查询 Flows"""
        return self.store.query(**kwargs)
    
    def get_stats(self) -> dict:
        """获取统计"""
        return self.store.get_stats()
    
    def export(self, flow_ids: List[str] = None, format: str = "json") -> str:
        """导出 Flows"""
        if flow_ids:
            flows = [self.store.get(fid) for fid in flow_ids if self.store.get(fid)]
        else:
            flows = list(self.store.flows)
        
        return json.dumps([f.to_dict() for f in flows], ensure_ascii=False, indent=2)

    def _write_flow_jsonl(self, flow: LLMFlow):
        """将 Flow 写入 JSONL 日志文件"""
        try:
            from .settings import get_settings
            settings = get_settings()
            if not settings.logging.api_log_enabled:
                return

            log_dir = settings.logging.log_dir / "flows"
            log_dir.mkdir(parents=True, exist_ok=True)

            today = datetime.now().strftime("%Y-%m-%d")
            log_file = log_dir / f"{today}.jsonl"
            max_chars = settings.logging.api_log_max_body_chars

            # 构建精简的日志记录
            record = {
                "id": flow.id,
                "timestamp": flow.timing.created_at,
                "completed_at": flow.timing.completed_at,
                "state": flow.state.value,
                "protocol": flow.protocol,
                "account_id": flow.account_id,
                "account_name": flow.account_name,
            }

            # 时间信息
            if flow.timing.ttfb_ms is not None:
                record["ttfb_ms"] = round(flow.timing.ttfb_ms, 1)
            if flow.timing.duration_ms is not None:
                record["duration_ms"] = round(flow.timing.duration_ms, 1)

            # 请求信息
            if flow.request:
                req_body = flow.request.body
                req_body_str = json.dumps(req_body, ensure_ascii=False) if req_body else ""
                if len(req_body_str) > max_chars:
                    req_body_str = req_body_str[:max_chars] + "...(truncated)"

                record["request"] = {
                    "method": flow.request.method,
                    "path": flow.request.path,
                    "model": flow.request.model,
                    "stream": flow.request.stream,
                    "message_count": len(flow.request.messages),
                    "has_tools": bool(flow.request.tools),
                    "has_system": bool(flow.request.system),
                    "body": req_body_str,
                }

            # 响应信息
            if flow.response:
                resp_content = flow.response.content or ""
                if len(resp_content) > max_chars:
                    resp_content = resp_content[:max_chars] + "...(truncated)"

                record["response"] = {
                    "status_code": flow.response.status_code,
                    "content": resp_content,
                    "stop_reason": flow.response.stop_reason,
                    "chunk_count": flow.response.chunk_count,
                    "tool_calls": flow.response.tool_calls,
                    "usage": asdict(flow.response.usage) if flow.response.usage else None,
                }

            # 错误信息
            if flow.error:
                record["error"] = asdict(flow.error)

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"写入 Flow JSONL 日志失败: {e}")


# 全局实例
flow_monitor = FlowMonitor(max_flows=500)
