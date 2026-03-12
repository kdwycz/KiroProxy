"""Anthropic 协议处理 - /v1/messages"""
import json
import uuid
import time
import asyncio
from curl_cffi import requests as curl_requests
from curl_cffi.requests.errors import RequestsError
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse

from ..config import KIRO_API_URL, map_model_name
from ..core import state, RetryableRequest, is_retryable_error, flow_monitor, TokenUsage, RetryContext, handle_429

from ..core.history_manager import HistoryManager, get_history_config, is_content_length_error, TruncateStrategy
from ..core.error_handler import classify_error, ErrorType, format_error_log
from ..core.rate_limiter import get_rate_limiter
from ..core.logger import logger
from ..credential import quota_manager
from ..kiro_api import build_headers, build_kiro_request, parse_event_stream_full, parse_event_stream, is_quota_exceeded_error
from ..converters import (
    generate_session_id,
    convert_anthropic_tools_to_kiro,
    convert_anthropic_messages_to_kiro,
    convert_kiro_response_to_anthropic,
    extract_images_from_content,
    inject_thinking_system_prefix
)


def _extract_text_from_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            parts.append(_extract_text_from_content(item))
        return "".join(parts)
    if isinstance(content, dict):
        if "text" in content and isinstance(content.get("text"), str):
            return content["text"]
        if "content" in content:
            return _extract_text_from_content(content.get("content"))
    return ""


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return (len(text) + 3) // 4


def _count_tokens_from_messages(messages, system: str = "") -> int:
    total = _estimate_tokens(system) if system else 0
    for msg in messages or []:
        total += _estimate_tokens(_extract_text_from_content(msg.get("content")))
    return total


def _handle_kiro_error(status_code: int, error_text: str, account):
    """处理 Kiro API 错误，返回 (http_status, error_type, error_message)"""
    error = classify_error(status_code, error_text)
    
    # 打印友好的错误日志
    logger.error(format_error_log(error, account.id if account else None))
    
    # 账号封禁 - 禁用账号
    if error.should_disable_account and account:
        account.enabled = False
        from ..credential import CredentialStatus
        account.status = CredentialStatus.SUSPENDED
        logger.warning(f"账号 {account.id} 已被禁用 (封禁)")
    
    # 配额超限 - 标记冷却
    elif error.type == ErrorType.RATE_LIMITED and account:
        account.mark_quota_exceeded(error.message[:100])
    
    # 映射错误类型
    error_type_map = {
        ErrorType.ACCOUNT_SUSPENDED: (403, "authentication_error"),
        ErrorType.RATE_LIMITED: (429, "rate_limit_error"),
        ErrorType.CONTENT_TOO_LONG: (400, "invalid_request_error"),
        ErrorType.AUTH_FAILED: (401, "authentication_error"),
        ErrorType.SERVICE_UNAVAILABLE: (503, "api_error"),
        ErrorType.MODEL_UNAVAILABLE: (503, "overloaded_error"),
        ErrorType.UNKNOWN: (500, "api_error"),
    }
    
    http_status, err_type = error_type_map.get(error.type, (500, "api_error"))
    return http_status, err_type, error.user_message, error


async def handle_count_tokens(request: Request):
    '''Handle /v1/messages/count_tokens requests.'''
    body = await request.json()
    messages = body.get("messages", [])
    system = body.get("system", "")
    if not messages and not system:
        raise HTTPException(400, "messages required")
    return {"input_tokens": _count_tokens_from_messages(messages, system)}


async def _call_kiro_for_summary(prompt: str, account, headers: dict) -> str:
    """调用 Kiro API 生成摘要（内部使用）"""
    kiro_request = build_kiro_request(prompt, "claude-haiku-4.5", [])  # 用快速模型生成摘要
    try:
        async with curl_requests.AsyncSession(verify=False, timeout=60) as client:
            resp = await client.post(KIRO_API_URL, json=kiro_request, headers=headers)
            if resp.status_code == 200:
                return parse_event_stream(resp.content)
    except Exception as e:
        logger.error(f"API 调用失败: {e}")
    return ""


async def handle_messages(request: Request):
    """处理 /v1/messages 请求"""
    start_time = time.time()
    log_id = uuid.uuid4().hex[:8]
    
    body = await request.json()
    model = map_model_name(body.get("model", "claude-sonnet-4"))
    messages = body.get("messages", [])
    system = body.get("system", "")
    stream = body.get("stream", False)
    tools = body.get("tools", [])
    thinking_param = body.get("thinking")  # Anthropic thinking 参数
    
    # Thinking 模式：注入 system prompt 前缀
    if thinking_param:
        system = inject_thinking_system_prefix(system, thinking_param)
    
    # 调试：打印原始请求的关键信息
    max_tokens = body.get("max_tokens", "-")
    system_info = f"{len(system)}ch" if system else "none"
    thinking_info = "on" if thinking_param else "off"
    est_tokens = _count_tokens_from_messages(messages, system if isinstance(system, str) else "")
    logger.info(
        f"Request: model={body.get('model')} -> {model}, "
        f"messages={len(messages)}, stream={stream}, "
        f"tools={len(tools)}, max_tokens={max_tokens}, "
        f"system={system_info}, thinking={thinking_info}, "
        f"est_input_tokens≈{est_tokens}"
    )
    
    if not messages:
        raise HTTPException(400, "messages required")
    
    session_id = generate_session_id(messages)
    account = state.get_available_account(session_id)
    
    if not account:
        raise HTTPException(503, "All accounts are rate limited or unavailable")
    
    logger.info(f"Account: {account.name} ({account.id})")
    
    # 创建 Flow 记录
    flow_id = flow_monitor.create_flow(
        protocol="anthropic",
        method="POST",
        path="/v1/messages",
        headers=dict(request.headers),
        body=body,
        account_id=account.id,
        account_name=account.name,
    )
    
    # 检查 token 是否即将过期，尝试刷新
    if account.is_token_expiring_soon(5):
        logger.info(f"Token 即将过期，尝试刷新: {account.id}")
        success, msg = await account.refresh_token()
        if not success:
            logger.error(f"Token 刷新失败: {msg}")
    
    token = account.get_token()
    if not token:
        flow_monitor.fail_flow(flow_id, "authentication_error", f"Failed to get token for account {account.name}")
        raise HTTPException(500, f"Failed to get token for account {account.name}")
    
    # 使用账号的动态 Machine ID（提前构建，供摘要使用）
    creds = account.get_credentials()
    headers = build_headers(
        token,
        machine_id=account.get_machine_id(),
        profile_arn=creds.profile_arn if creds else None,
        client_id=creds.client_id if creds else None
    )
    
    # 限速检查
    rate_limiter = get_rate_limiter()
    can_request, wait_seconds, reason = rate_limiter.can_request(account.id)
    if not can_request:
        logger.info(f"限速: {reason}")
        await asyncio.sleep(wait_seconds)
    
    # 转换消息格式
    user_content, history, tool_results = convert_anthropic_messages_to_kiro(messages, system)
    
    # 历史消息预处理
    history_manager = HistoryManager(get_history_config(), cache_key=session_id)
    
    # 检查是否需要智能摘要或错误重试预摘要
    async def api_caller(prompt: str) -> str:
        return await _call_kiro_for_summary(prompt, account, headers)
    if history_manager.should_summarize(history) or history_manager.should_pre_summary_for_error_retry(history, user_content):
        history = await history_manager.pre_process_async(history, user_content, api_caller)
    else:
        history = history_manager.pre_process(history, user_content)
    
    # 摘要/截断后再次修复历史交替和 toolUses/toolResults 配对
    from ..converters import fix_history_alternation
    history = fix_history_alternation(history)
    
    if history_manager.was_truncated:
        logger.info(f"{history_manager.truncate_info}")
    
    # 提取最后一条消息中的图片
    images = []
    if messages:
        last_msg = messages[-1]
        if last_msg.get("role") == "user":
            _, images = extract_images_from_content(last_msg.get("content", ""))
    
    # 构建 Kiro 请求
    kiro_tools = convert_anthropic_tools_to_kiro(tools) if tools else None
    kiro_request = build_kiro_request(user_content, model, history, kiro_tools, images, tool_results)
    
    if stream:
        return await _handle_stream(kiro_request, headers, account, model, log_id, start_time, session_id, flow_id, history, user_content, kiro_tools, images, tool_results, history_manager, thinking_enabled=bool(thinking_param))
    else:
        return await _handle_non_stream(kiro_request, headers, account, model, log_id, start_time, session_id, flow_id, history, user_content, kiro_tools, images, tool_results, history_manager, thinking_enabled=bool(thinking_param))



def _extract_stream_content(buffer: bytes, parse_pos: int) -> tuple:
    """从 AWS event-stream 累积缓冲区中提取文本内容
    
    独立于 generate() 生成器函数，避免 Python 3.12+ 中
    json= 关键字参数导致的作用域冲突。
    
    Returns:
        (results, new_parse_pos)
        results: list of (content_str, json_escaped_str)
    """
    results = []
    
    while parse_pos < len(buffer):
        if parse_pos + 12 > len(buffer):
            break
        total_len = int.from_bytes(buffer[parse_pos:parse_pos+4], 'big')
        if total_len == 0 or total_len > len(buffer) - parse_pos:
            break
        headers_len = int.from_bytes(buffer[parse_pos+4:parse_pos+8], 'big')
        payload_start = parse_pos + 12 + headers_len
        payload_end = parse_pos + total_len - 4

        if payload_start < payload_end:
            try:
                payload = json.loads(buffer[payload_start:payload_end].decode('utf-8'))
                content = None
                if 'assistantResponseEvent' in payload:
                    content = payload['assistantResponseEvent'].get('content')
                elif 'content' in payload:
                    header_str = buffer[parse_pos+12:parse_pos+12+headers_len].decode('utf-8', errors='ignore')
                    if 'toolUseEvent' not in header_str:
                        content = payload['content']
                if content:
                    results.append((content, json.dumps(content)))
            except Exception:
                pass
        parse_pos += total_len
    
    return results, parse_pos


async def _handle_stream(kiro_request, headers, account, model, log_id, start_time, session_id=None, flow_id=None, history=None, user_content="", kiro_tools=None, images=None, tool_results=None, history_manager=None, thinking_enabled=False):
    """Handle streaming responses with two-phase 429 retry strategy."""
    
    async def generate():
        nonlocal kiro_request, history
        current_account = account
        retry_count = 0
        max_retries = max(len(state.accounts), 3)
        retry_ctx = RetryContext()
        full_content = ""
        
        while retry_count <= max_retries:
            try:
                async with curl_requests.AsyncSession(verify=False, timeout=300) as client:
                    response = await client.post(KIRO_API_URL, data=json.dumps(kiro_request), headers=headers, stream=True)
                        
                    # 处理配额超限
                    if response.status_code == 429 or is_quota_exceeded_error(response.status_code, ""):
                        current_account, should_continue = await handle_429(
                            current_account, headers, retry_ctx, "stream"
                        )
                        if should_continue:
                            retry_count += 1
                            continue

                        if flow_id:
                            flow_monitor.fail_flow(flow_id, "rate_limit_error", "All accounts rate limited", 429)
                        yield f'event: error\ndata: {{"type":"error","error":{{"type":"rate_limit_error","message":"All accounts rate limited"}}}}\n\n'
                        return

                    # 处理可重试的服务端错误
                    if is_retryable_error(response.status_code):
                        if retry_count < max_retries:
                            logger.error(f"服务端错误 {response.status_code}，重试 {retry_count + 1}/{max_retries}")
                            retry_count += 1
                            await asyncio.sleep(0.5 * (2 ** retry_count))
                            continue
                        if flow_id:
                            flow_monitor.fail_flow(flow_id, "api_error", "Server error after retries", response.status_code)
                        yield f'event: error\ndata: {{"type":"error","error":{{"type":"api_error","message":"Server error after retries"}}}}\n\n'
                        return

                    if response.status_code != 200:
                        error_text = response.content
                        error_str = error_text if isinstance(error_text, str) else error_text.decode()
                        logger.error(f"=== Kiro API Error ===")
                        logger.info(f"Status: {response.status_code}")
                        logger.error(f"Response: {error_str[:500]}")
                        logger.info(f"Request model: {model}")
                        logger.info(f"History len: {len(history) if history else 0}")
                        logger.info(f"Tool results: {len(tool_results) if tool_results else 0}")
                        # 对于 400 错误，打印更多请求细节
                        if response.status_code == 400:
                            logger.debug(f"Kiro request dumped to /tmp/kiro_400_request.json")
                            try:
                                with open("/tmp/kiro_400_request.json", "w", encoding="utf-8") as f:
                                    json.dump(kiro_request, f, ensure_ascii=False, indent=2)
                            except Exception as e:
                                logger.error(f"Dump error: {e}")

                            logger.debug(f"Kiro request keys: {list(kiro_request.keys())}")
                            if 'conversationState' in kiro_request:
                                cs = kiro_request['conversationState']
                                logger.info(f"  conversationState keys: {list(cs.keys())}")
                                if 'currentMessage' in cs:
                                    cm = cs['currentMessage']
                                    logger.info(f"  currentMessage keys: {list(cm.keys())}")
                                    if 'userInputMessage' in cm:
                                        uim = cm['userInputMessage']
                                        logger.info(f"  userInputMessage keys: {list(uim.keys())}")
                                        content = uim.get('content', '')
                                        logger.debug(f"  content (first 200 chars): {str(content)[:200]}")
                                if 'history' in cs:
                                    hist = cs['history']
                                    logger.info(f"  history count: {len(hist) if hist else 0}")
                                    if hist:
                                        for i, h in enumerate(hist[:3]):
                                            logger.debug(f"    history[{i}] keys: {list(h.keys()) if isinstance(h, dict) else type(h)}")
                        logger.info(f"======================")
                        
                        # 使用统一的错误处理
                        http_status, error_type, error_msg, error_obj = _handle_kiro_error(
                            response.status_code, error_str, current_account
                        )
                        
                        # 账号封禁 - 尝试切换账号
                        if error_obj.should_switch_account:
                            retry_ctx.tried_accounts.add(current_account.id)
                            next_account = state.get_next_available_account(exclude_ids=retry_ctx.tried_accounts)
                            if next_account and retry_count < max_retries:
                                logger.info(f"切换账号: {current_account.id} -> {next_account.id}")
                                current_account = next_account
                                headers["Authorization"] = f"Bearer {current_account.get_token()}"
                                retry_count += 1
                                continue
                        
                        # 检查是否为内容长度超限错误，尝试截断重试
                        if error_obj.type == ErrorType.CONTENT_TOO_LONG:
                            history_chars, user_chars, total_chars = history_manager.estimate_request_chars(
                                history, user_content
                            )
                            logger.info(f"内容长度超限: history={history_chars} chars, user={user_chars} chars, total={total_chars} chars")
                            async def api_caller(prompt: str) -> str:
                                return await _call_kiro_for_summary(prompt, current_account, headers)
                            truncated_history, should_retry = await history_manager.handle_length_error_async(
                                history, retry_count, api_caller
                            )
                            if should_retry:
                                logger.info(f"内容长度超限，{history_manager.truncate_info}")
                                history = truncated_history
                                # 重新构建请求
                                kiro_request = build_kiro_request(user_content, model, history, kiro_tools, images, tool_results)
                                retry_count += 1
                                continue
                        
                        if flow_id:
                            flow_monitor.fail_flow(flow_id, error_type, error_msg, response.status_code, error_str)
                        yield f'event: error\ndata: {{"type":"error","error":{{"type":"{error_type}","message":"{error_msg}"}}}}\n\n'
                        return

                    # 标记开始流式传输
                    if flow_id:
                        flow_monitor.start_streaming(flow_id)

                    # 正常处理响应
                    msg_id = f"msg_{log_id}"
                    yield f'event: message_start\ndata: {{"type":"message_start","message":{{"id":"{msg_id}","type":"message","role":"assistant","content":[],"model":"{model}","stop_reason":null,"stop_sequence":null,"usage":{{"input_tokens":0,"output_tokens":0}}}}}}\n\n'
                    yield f'event: content_block_start\ndata: {{"type":"content_block_start","index":0,"content_block":{{"type":"text","text":""}}}}\n\n'
                    yield f'event: ping\ndata: {{"type":"ping"}}\n\n'

                    full_response = b""
                    parse_pos = 0

                    async for chunk in response.aiter_content():
                        full_response += chunk

                        # 从累积缓冲区提取新的完整帧
                        extracted, parse_pos = _extract_stream_content(full_response, parse_pos)
                        for content, content_json in extracted:
                            full_content += content
                            if flow_id:
                                flow_monitor.add_chunk(flow_id, content)
                            yield f'event: content_block_delta\ndata: {{"type":"content_block_delta","index":0,"delta":{{"type":"text_delta","text":{content_json}}}}}\n\n'

                    result = parse_event_stream_full(full_response)

                    yield f'event: content_block_stop\ndata: {{"type":"content_block_stop","index":0}}\n\n'

                    if result["tool_uses"]:
                        for i, tool_use in enumerate(result["tool_uses"], 1):
                            yield f'event: content_block_start\ndata: {{"type":"content_block_start","index":{i},"content_block":{{"type":"tool_use","id":"{tool_use["id"]}","name":"{tool_use["name"]}","input":{{}}}}}}\n\n'
                            yield f'event: content_block_delta\ndata: {{"type":"content_block_delta","index":{i},"delta":{{"type":"input_json_delta","partial_json":{json.dumps(json.dumps(tool_use["input"]))}}}}}\n\n'
                            yield f'event: content_block_stop\ndata: {{"type":"content_block_stop","index":{i}}}\n\n'

                    stop_reason = result["stop_reason"]
                    output_tokens = result.get("output_tokens", 0)
                    yield f'event: message_delta\ndata: {{"type":"message_delta","delta":{{"stop_reason":"{stop_reason}","stop_sequence":null}},"usage":{{"output_tokens":{output_tokens}}}}}\n\n'
                    yield f'event: message_stop\ndata: {{"type":"message_stop"}}\n\n'

                    # 完成 Flow
                    if flow_id:
                        flow_monitor.complete_flow(
                            flow_id,
                            status_code=200,
                            content=full_content,
                            tool_calls=result.get("tool_uses", []),
                            stop_reason=stop_reason,
                            usage=TokenUsage(
                                input_tokens=result.get("input_tokens", 0),
                                output_tokens=result.get("output_tokens", 0),
                            ),
                        )

                    current_account.reset_quota_backoff()  # 成功后重置退避
                    get_rate_limiter().record_request(current_account.id)
                    return

            except RequestsError as e:
                error_str = str(e).lower()
                is_timeout = "timeout" in error_str or "timed out" in error_str
                label = "请求超时" if is_timeout else "连接错误"
                error_code = "timeout_error" if is_timeout else "connection_error"
                error_status = 408 if is_timeout else 502
                if retry_count < max_retries:
                    logger.info(f"{label}，重试 {retry_count + 1}/{max_retries}")
                    retry_count += 1
                    await asyncio.sleep(0.5 * (2 ** retry_count))
                    continue
                if flow_id:
                    flow_monitor.fail_flow(flow_id, error_code, f"{label} after retries", error_status)
                yield f'event: error\ndata: {{"type":"error","error":{{"type":"api_error","message":"{label} after retries"}}}}\n\n'
                return
            except Exception as e:
                # 检查是否为可重试的网络错误
                if is_retryable_error(None, e) and retry_count < max_retries:
                    logger.error(f"网络错误，重试 {retry_count + 1}/{max_retries}: {type(e).__name__}")
                    retry_count += 1
                    await asyncio.sleep(0.5 * (2 ** retry_count))
                    continue
                if flow_id:
                    flow_monitor.fail_flow(flow_id, "api_error", str(e), 500)
                yield f'event: error\ndata: {{"type":"error","error":{{"type":"api_error","message":"{str(e)}"}}}}\n\n'
                return

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _handle_non_stream(kiro_request, headers, account, model, log_id, start_time, session_id=None, flow_id=None, history=None, user_content="", kiro_tools=None, images=None, tool_results=None, history_manager=None, thinking_enabled=False):
    """Handle non-streaming responses with two-phase 429 retry strategy.
    
    Phase 1: Sleep 2s and retry same account (covers most transient rate limits)
    Phase 2: Mark cooldown (exponential backoff), switch accounts or wait shortest cooldown
    """
    error_msg = None
    status_code = 200
    current_account = account
    rate_ctx = RetryContext()
    max_retries = max(len(state.accounts), 3)
    retry_ctx = RetryableRequest(max_retries=max_retries)
    should_log = False

    for retry in range(max_retries + 1):
        should_log = False
        try:
            async with curl_requests.AsyncSession(verify=False, timeout=300) as client:
                response = await client.post(KIRO_API_URL, json=kiro_request, headers=headers)
                status_code = response.status_code

                # 处理配额超限 (429)
                if response.status_code == 429 or is_quota_exceeded_error(response.status_code, response.text):
                    current_account, should_continue = await handle_429(
                        current_account, headers, rate_ctx, "anthropic"
                    )
                    if should_continue:
                        continue
                    if flow_id:
                        flow_monitor.fail_flow(flow_id, "rate_limit_error", "All accounts rate limited", 429)
                    raise HTTPException(429, "All accounts rate limited")

                # 处理可重试的服务端错误
                if is_retryable_error(response.status_code):
                    if retry < max_retries:
                        logger.error(f"服务端错误 {response.status_code}，重试 {retry + 1}/{max_retries}")
                        await retry_ctx.wait()
                        continue
                    if flow_id:
                        flow_monitor.fail_flow(flow_id, "api_error", f"Server error after {max_retries} retries", response.status_code)
                    raise HTTPException(response.status_code, f"Server error after {max_retries} retries")

                if response.status_code != 200:
                    error_msg = response.text
                    logger.error(f"Kiro API Error {response.status_code}: {error_msg[:500]}")
                    
                    # 使用统一的错误处理
                    status, error_type, error_message, error_obj = _handle_kiro_error(
                        response.status_code, error_msg, current_account
                    )
                    
                    # 账号封禁或配额超限 - 尝试切换账号
                    if error_obj.should_switch_account:
                        rate_ctx.tried_accounts.add(current_account.id)
                        next_account = state.get_next_available_account(exclude_ids=rate_ctx.tried_accounts)
                        if next_account and retry < max_retries:
                            logger.info(f"切换账号: {current_account.id} -> {next_account.id}")
                            current_account = next_account
                            headers["Authorization"] = f"Bearer {current_account.get_token()}"
                            continue
                    
                    # 检查是否为内容长度超限错误，尝试截断重试
                    if error_obj.type == ErrorType.CONTENT_TOO_LONG and history_manager:
                        history_chars, user_chars, total_chars = history_manager.estimate_request_chars(
                            history, user_content
                        )
                        logger.info(f"内容长度超限: history={history_chars} chars, user={user_chars} chars, total={total_chars} chars")
                        async def api_caller(prompt: str) -> str:
                            return await _call_kiro_for_summary(prompt, current_account, headers)
                        truncated_history, should_retry = await history_manager.handle_length_error_async(
                            history, retry, api_caller
                        )
                        if should_retry:
                            logger.info(f"内容长度超限，{history_manager.truncate_info}")
                            history = truncated_history
                            kiro_request = build_kiro_request(user_content, model, history, kiro_tools, images, tool_results)
                            continue
                        else:
                            logger.info(f"内容长度超限但未重试: retry={retry}/{max_retries}")
                    
                    if flow_id:
                        flow_monitor.fail_flow(flow_id, error_type, error_message, status, error_msg)
                    raise HTTPException(status, error_message)

                result = parse_event_stream_full(response.content)
                current_account.reset_quota_backoff()  # 成功后重置退避
                get_rate_limiter().record_request(current_account.id)

                # 完成 Flow
                if flow_id:
                    flow_monitor.complete_flow(
                        flow_id,
                        status_code=200,
                        content=result.get("text", ""),
                        tool_calls=result.get("tool_uses", []),
                        stop_reason=result.get("stop_reason", ""),
                        usage=TokenUsage(
                            input_tokens=result.get("input_tokens", 0),
                            output_tokens=result.get("output_tokens", 0),
                        ),
                    )

                should_log = True
                return convert_kiro_response_to_anthropic(result, model, f"msg_{log_id}", thinking_enabled=thinking_enabled)

        except HTTPException:
            should_log = True
            raise
        except RequestsError as e:
            error_str = str(e).lower()
            is_timeout = "timeout" in error_str or "timed out" in error_str
            label = "Request timeout" if is_timeout else "Connection error"
            error_code = "timeout_error" if is_timeout else "connection_error"
            error_status = 408 if is_timeout else 502
            error_msg = f"{label}: {e}"
            status_code = error_status
            if retry < max_retries:
                logger.info(f"{label}，重试 {retry + 1}/{max_retries}")
                await retry_ctx.wait()
                continue
            if flow_id:
                flow_monitor.fail_flow(flow_id, error_code, f"{label} after retries", error_status)
            should_log = True
            raise HTTPException(error_status, f"{label} after retries")
        except Exception as e:
            error_msg = str(e)
            status_code = 500
            # 检查是否为可重试的网络错误
            if is_retryable_error(None, e) and retry < max_retries:
                logger.error(f"网络错误，重试 {retry + 1}/{max_retries}: {type(e).__name__}")
                await retry_ctx.wait()
                continue
            if flow_id:
                flow_monitor.fail_flow(flow_id, "api_error", str(e), 500)
            should_log = True
            raise HTTPException(500, str(e))
        finally:
            pass
    
    raise HTTPException(503, "All retries exhausted")

