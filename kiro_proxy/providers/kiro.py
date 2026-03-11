"""Kiro Provider"""
import json
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple

# Kiro API 总上下文窗口大小（tokens），用于从 contextUsagePercentage 计算 token 数
TOTAL_CONTEXT_TOKENS = 172500

from .base import BaseProvider
from ..credential import (
    KiroCredentials, TokenRefresher,
    generate_machine_id, get_kiro_version, get_system_info
)


class KiroProvider(BaseProvider):
    """Kiro/CodeWhisperer Provider"""
    
    API_URL = "https://q.us-east-1.amazonaws.com/generateAssistantResponse"
    MODELS_URL = "https://q.us-east-1.amazonaws.com/ListAvailableModels"
    
    def __init__(self, credentials: Optional[KiroCredentials] = None):
        self.credentials = credentials
        self._machine_id: Optional[str] = None
    
    @property
    def name(self) -> str:
        return "kiro"
    
    @property
    def api_url(self) -> str:
        return self.API_URL
    
    def get_machine_id(self) -> str:
        """获取基于凭证的 Machine ID"""
        if self._machine_id:
            return self._machine_id
        
        if self.credentials:
            self._machine_id = generate_machine_id(
                self.credentials.profile_arn,
                self.credentials.client_id
            )
        else:
            self._machine_id = generate_machine_id()
        
        return self._machine_id
    
    def build_headers(
        self, 
        token: str, 
        agent_mode: str = "vibe",
        **kwargs
    ) -> Dict[str, str]:
        """构建 Kiro API 请求头"""
        machine_id = kwargs.get("machine_id") or self.get_machine_id()
        kiro_version = get_kiro_version()
        os_name, node_version = get_system_info()
        
        return {
            "content-type": "application/json",
            "x-amzn-codewhisperer-optout": "true",
            "x-amzn-kiro-agent-mode": agent_mode,
            "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{kiro_version}-{machine_id}",
            "user-agent": f"aws-sdk-js/1.0.0 ua/2.1 os/{os_name} lang/js md/nodejs#{node_version} api/codewhispererruntime#1.0.0 m/E KiroIDE-{kiro_version}-{machine_id}",
            "amz-sdk-invocation-id": str(uuid.uuid4()),
            "amz-sdk-request": "attempt=1; max=1",
            "Authorization": f"Bearer {token}",
            "Connection": "close",
        }
    
    def build_request(
        self,
        messages: list = None,
        model: str = "claude-sonnet-4",
        user_content: str = "",
        history: List[dict] = None,
        tools: List[dict] = None,
        images: List[dict] = None,
        tool_results: List[dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """构建 Kiro API 请求体"""
        conversation_id = str(uuid.uuid4())
        
        # 确保 content 不为空
        if not user_content:
            user_content = "Continue"
        
        user_input_message = {
            "content": user_content,
            "modelId": model,
            "origin": "AI_EDITOR",
        }
        
        if images:
            user_input_message["images"] = images
        
        # 只有在有 tools 或 tool_results 时才添加 userInputMessageContext
        context = {}
        if tools:
            context["tools"] = tools
        if tool_results:
            context["toolResults"] = tool_results
        
        if context:
            user_input_message["userInputMessageContext"] = context
        
        return {
            "conversationState": {
                "agentContinuationId": str(uuid.uuid4()),
                "agentTaskType": "vibe",
                "chatTriggerType": "MANUAL",
                "conversationId": conversation_id,
                "currentMessage": {"userInputMessage": user_input_message},
                "history": history or []
            }
        }
    
    def parse_response(self, raw: bytes) -> Dict[str, Any]:
        """解析 AWS event-stream 格式响应
        
        返回:
            dict with keys:
                content: list[str] — 文本片段
                tool_uses: list[dict] — 工具调用
                stop_reason: str — "end_turn" or "tool_use"
                context_usage_percentage: float|None — 上下文使用百分比
                input_tokens: int — 估算的输入 token 数
                output_tokens: int — 估算的输出 token 数
        """
        result = {
            "content": [],
            "tool_uses": [],
            "stop_reason": "end_turn",
            "context_usage_percentage": None,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        
        tool_input_buffer = {}
        pos = 0
        
        while pos < len(raw):
            if pos + 12 > len(raw):
                break
            
            total_len = int.from_bytes(raw[pos:pos+4], 'big')
            headers_len = int.from_bytes(raw[pos+4:pos+8], 'big')
            
            if total_len == 0 or total_len > len(raw) - pos:
                break
            
            header_start = pos + 12
            header_end = header_start + headers_len
            headers_data = raw[header_start:header_end]
            event_type = None
            
            try:
                headers_str = headers_data.decode('utf-8', errors='ignore')
                if 'toolUseEvent' in headers_str:
                    event_type = 'toolUseEvent'
                elif 'assistantResponseEvent' in headers_str:
                    event_type = 'assistantResponseEvent'
                elif 'exception' in headers_str:
                    event_type = 'exception'
            except:
                pass
            
            payload_start = pos + 12 + headers_len
            payload_end = pos + total_len - 4
            
            if payload_start < payload_end:
                try:
                    payload = json.loads(raw[payload_start:payload_end].decode('utf-8'))
                    
                    # Exception 事件处理（如 ContentLengthExceededException）
                    if event_type == 'exception' or '__type' in payload:
                        exc_type = payload.get('__type', '')
                        if 'ContentLength' in exc_type or 'Exceeded' in exc_type:
                            result["stop_reason"] = "max_tokens"
                        else:
                            result["stop_reason"] = "max_tokens"  # 所有 exception 都视为截断
                        pos += total_len
                        continue
                    
                    if 'assistantResponseEvent' in payload:
                        e = payload['assistantResponseEvent']
                        if 'content' in e:
                            result["content"].append(e['content'])
                    elif 'content' in payload and event_type != 'toolUseEvent':
                        result["content"].append(payload['content'])
                    
                    # contextUsagePercentage：支持顶层和嵌套两种格式
                    if 'contextUsagePercentage' in payload:
                        result["context_usage_percentage"] = payload['contextUsagePercentage']
                    elif 'contextUsageEvent' in payload:
                        cue = payload['contextUsageEvent']
                        if isinstance(cue, dict) and 'contextUsagePercentage' in cue:
                            result["context_usage_percentage"] = cue['contextUsagePercentage']
                    
                    if event_type == 'toolUseEvent' or 'toolUseId' in payload:
                        tool_id = payload.get('toolUseId', '')
                        tool_name = payload.get('name', '')
                        tool_input = payload.get('input', '')
                        
                        if tool_id:
                            if tool_id not in tool_input_buffer:
                                tool_input_buffer[tool_id] = {
                                    "id": tool_id,
                                    "name": tool_name,
                                    "input_parts": []
                                }
                            if tool_name and not tool_input_buffer[tool_id]["name"]:
                                tool_input_buffer[tool_id]["name"] = tool_name
                            if tool_input:
                                tool_input_buffer[tool_id]["input_parts"].append(tool_input)
                except:
                    pass
            
            pos += total_len
        
        # 组装工具调用
        for tool_id, tool_data in tool_input_buffer.items():
            input_parts = tool_data["input_parts"]
            
            # 空输入（工具无必填参数）→ 使用空对象
            if not input_parts:
                input_json = {}
            else:
                input_str = "".join(input_parts)
                # 尝试直接解析（增量模式下拼接可用）
                try:
                    input_json = json.loads(input_str)
                except (json.JSONDecodeError, ValueError):
                    # 累积模式修复：Kiro 可能发送累积式输入
                    # 每次发送截止当前的全部内容，而非增量
                    # 例如: '{"path"' + '{"path": "/a.txt"' + '{"path": "/a.txt", "content": "hello"}'
                    # 此时只取最后一个能被解析的部分
                    input_json = self._repair_tool_input(input_parts)
            
            result["tool_uses"].append({
                "type": "tool_use",
                "id": tool_data["id"],
                "name": tool_data["name"],
                "input": input_json
            })
        
        if result["tool_uses"]:
            result["stop_reason"] = "tool_use"
        
        # 计算 token 数
        full_text = "".join(result["content"])
        output_tokens = max(1, (len(full_text) + 3) // 4)  # 粗略估算
        for tu in result["tool_uses"]:
            output_tokens += (len(json.dumps(tu.get("input", {}))) + 3) // 4
        result["output_tokens"] = output_tokens
        
        if result["context_usage_percentage"] is not None and result["context_usage_percentage"] > 0:
            total_tokens = round(TOTAL_CONTEXT_TOKENS * result["context_usage_percentage"] / 100)
            result["input_tokens"] = max(0, total_tokens - output_tokens)
        
        return result
    
    def _repair_tool_input(self, parts: list) -> dict:
        """修复累积式工具输入
        
        Kiro 有时会发送累积式输入（每次包含截止当前的全部内容），
        而非增量式输入（每次只发送新增部分）。
        
        策略：从最后一个 part 开始逆序尝试 json.loads，
        第一个能解析成功的就是完整的输入。
        """
        # 逆序尝试每个 part
        for part in reversed(parts):
            try:
                return json.loads(part)
            except (json.JSONDecodeError, ValueError):
                continue
        
        # 都解析不了，返回原始拼接字符串
        return {"raw": "".join(parts)}
    
    def parse_response_text(self, raw: bytes) -> str:
        """解析响应，只返回文本内容"""
        result = self.parse_response(raw)
        return "".join(result["content"]) or "[No response]"
    
    @staticmethod
    def parse_thinking_blocks(text: str) -> list:
        """解析包含 <thinking> 标签的文本，拆分为 Anthropic 兼容的 content blocks
        
        Returns:
            list of dicts, e.g.:
            [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]
        """
        blocks = []
        pattern = re.compile(r'<thinking>(.*?)</thinking>', re.DOTALL)
        last_end = 0
        
        for match in pattern.finditer(text):
            # 思考块之前的文本
            before = text[last_end:match.start()].strip()
            if before:
                blocks.append({"type": "text", "text": before})
            # 思考块
            thinking_text = match.group(1).strip()
            if thinking_text:
                blocks.append({"type": "thinking", "thinking": thinking_text})
            last_end = match.end()
        
        # 思考块之后的文本
        after = text[last_end:].strip()
        if after:
            blocks.append({"type": "text", "text": after})
        
        # 如果没有 thinking 标签，返回原始文本
        if not blocks:
            blocks.append({"type": "text", "text": text})
        
        return blocks
    
    async def refresh_token(self) -> Tuple[bool, str]:
        """刷新 token"""
        if not self.credentials:
            return False, "无凭证信息"
        
        refresher = TokenRefresher(self.credentials)
        return await refresher.refresh()
    
    def is_quota_exceeded(self, status_code: int, error_text: str) -> bool:
        """检查是否为配额超限错误"""
        if status_code in {429, 503, 529}:
            return True
        
        keywords = ["rate limit", "quota", "too many requests", "throttl"]
        error_lower = error_text.lower()
        return any(kw in error_lower for kw in keywords)
