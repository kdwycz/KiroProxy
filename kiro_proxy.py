#!/usr/bin/env python3
"""
Kiro API 反向代理服务器
对外暴露 OpenAI 兼容接口，内部调用 Kiro/AWS Q API
"""

import json
import uuid
import os
from curl_cffi import requests as curl_requests
from curl_cffi.requests import RequestsError
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Kiro API Proxy")

# Kiro API 配置
KIRO_API_URL = "https://q.us-east-1.amazonaws.com/generateAssistantResponse"
TOKEN_PATH = Path.home() / ".aws/sso/cache/kiro-auth-token.json"
MACHINE_ID = "fa41d5def91e29225c73f6ea8ee0941a87bd812aae5239e3dde72c3ba7603a26"

def get_kiro_token() -> str:
    """从本地文件读取 Kiro token"""
    try:
        with open(TOKEN_PATH) as f:
            data = json.load(f)
            return data.get("accessToken", "")
    except Exception as e:
        logger.error(f"读取 token 失败: {e}")
        raise HTTPException(status_code=500, detail="无法读取 Kiro token")

def build_kiro_headers(token: str) -> dict:
    """构建 Kiro API 请求头"""
    return {
        "content-type": "application/json",
        "x-amzn-codewhisperer-optout": "true",
        "x-amzn-kiro-agent-mode": "vibe",
        "x-amz-user-agent": f"aws-sdk-js/1.0.27 KiroIDE-0.8.0-{MACHINE_ID}",
        "user-agent": f"aws-sdk-js/1.0.27 ua/2.1 os/linux lang/js md/nodejs api/codewhispererstreaming KiroIDE-0.8.0-{MACHINE_ID}",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
        "Authorization": f"Bearer {token}",
    }

def build_kiro_request(messages: list, model: str, conversation_id: str = None) -> dict:
    """将 OpenAI 格式转换为 Kiro 格式"""
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    # 提取最后一条用户消息
    user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break
    
    return {
        "conversationState": {
            "conversationId": conversation_id,
            "currentMessage": {
                "userInputMessage": {
                    "content": user_content,
                    "modelId": model.replace("kiro-", ""),  # 移除前缀
                    "origin": "AI_EDITOR",
                    "userInputMessageContext": {}
                }
            },
            "chatTriggerType": "MANUAL"
        }
    }

def parse_kiro_response(response_data: dict) -> str:
    """解析 Kiro 响应，提取 AI 回复内容"""
    try:
        # Kiro 响应格式可能是流式的，需要解析
        if isinstance(response_data, dict):
            # 尝试多种可能的响应路径
            if "generateAssistantResponseResponse" in response_data:
                resp = response_data["generateAssistantResponseResponse"]
                if "assistantResponseEvent" in resp:
                    event = resp["assistantResponseEvent"]
                    if "content" in event:
                        return event["content"]
            
            # 直接返回文本内容
            if "content" in response_data:
                return response_data["content"]
            
            if "message" in response_data:
                return response_data["message"]
        
        return json.dumps(response_data)
    except Exception as e:
        logger.error(f"解析响应失败: {e}")
        return str(response_data)

def parse_event_stream(raw_content: bytes) -> str:
    """解析 AWS event-stream 格式的响应"""
    try:
        # 尝试直接解码为 UTF-8
        try:
            text = raw_content.decode('utf-8')
            # 如果是纯 JSON
            if text.startswith('{'):
                data = json.loads(text)
                return parse_kiro_response(data)
        except:
            pass
        
        # AWS event-stream 格式解析
        # 格式: [prelude (8 bytes)][headers][payload][message CRC (4 bytes)]
        content_parts = []
        pos = 0
        
        while pos < len(raw_content):
            if pos + 12 > len(raw_content):
                break
            
            # 读取 prelude: total_length (4 bytes) + headers_length (4 bytes) + prelude_crc (4 bytes)
            total_length = int.from_bytes(raw_content[pos:pos+4], 'big')
            headers_length = int.from_bytes(raw_content[pos+4:pos+8], 'big')
            
            if total_length == 0 or total_length > len(raw_content) - pos:
                break
            
            # 跳过 prelude (12 bytes) 和 headers
            payload_start = pos + 12 + headers_length
            payload_end = pos + total_length - 4  # 减去 message CRC
            
            if payload_start < payload_end:
                payload = raw_content[payload_start:payload_end]
                try:
                    # 尝试解析 payload 为 JSON
                    payload_text = payload.decode('utf-8')
                    if payload_text.strip():
                        payload_json = json.loads(payload_text)
                        
                        # 提取文本内容
                        if "assistantResponseEvent" in payload_json:
                            event = payload_json["assistantResponseEvent"]
                            if "content" in event:
                                content_parts.append(event["content"])
                        elif "content" in payload_json:
                            content_parts.append(payload_json["content"])
                        elif "text" in payload_json:
                            content_parts.append(payload_json["text"])
                        else:
                            logger.info(f"   Event: {payload_text[:200]}")
                except Exception as e:
                    logger.debug(f"解析 payload 失败: {e}")
            
            pos += total_length
        
        if content_parts:
            return "".join(content_parts)
        
        # 如果解析失败，返回原始内容的十六进制表示用于调试
        return f"[无法解析响应，原始数据: {raw_content[:500].hex()}]"
        
    except Exception as e:
        logger.error(f"解析 event-stream 失败: {e}")
        return f"[解析错误: {e}]"

@app.get("/")
async def root():
    """健康检查"""
    token_exists = TOKEN_PATH.exists()
    return {
        "status": "ok",
        "service": "Kiro API Proxy",
        "token_available": token_exists,
        "endpoints": {
            "chat": "/v1/chat/completions",
            "models": "/v1/models"
        }
    }

@app.get("/v1/models")
async def list_models():
    """列出可用模型 (OpenAI 兼容)"""
    return {
        "object": "list",
        "data": [
            {"id": "kiro-claude-sonnet-4", "object": "model", "owned_by": "kiro"},
            {"id": "kiro-claude-opus-4.5", "object": "model", "owned_by": "kiro"},
            {"id": "claude-sonnet-4", "object": "model", "owned_by": "kiro"},
            {"id": "claude-opus-4.5", "object": "model", "owned_by": "kiro"},
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI 兼容的聊天接口"""
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    messages = body.get("messages", [])
    model = body.get("model", "claude-sonnet-4")
    stream = body.get("stream", False)
    
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    
    # 获取 token
    token = get_kiro_token()
    
    # 构建请求
    headers = build_kiro_headers(token)
    kiro_body = build_kiro_request(messages, model)
    
    logger.info(f"📤 发送请求到 Kiro API, model={model}")
    logger.info(f"   消息: {messages[-1].get('content', '')[:100]}...")
    
    try:
        async with curl_requests.AsyncSession(verify=False, timeout=60) as client:
            response = await client.post(
                KIRO_API_URL,
                headers=headers,
                json=kiro_body
            )
            
            logger.info(f"📥 Kiro 响应状态: {response.status_code}")
            logger.info(f"   Content-Type: {response.headers.get('content-type')}")
            
            if response.status_code != 200:
                logger.error(f"Kiro API 错误: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Kiro API error: {response.text}"
                )
            
            # 处理响应 - 可能是 event-stream 或 JSON
            raw_content = response.content
            logger.info(f"   响应大小: {len(raw_content)} bytes")
            logger.info(f"   原始响应前200字节: {raw_content[:200]}")
            
            content = parse_event_stream(raw_content)
            
            logger.info(f"   回复: {content[:100]}...")
            
            # 返回 OpenAI 兼容格式
            return JSONResponse({
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(datetime.now().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            })
            
    except RequestsError as e:
        logger.error(f"请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"未知错误: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/token/status")
async def token_status():
    """检查 token 状态"""
    try:
        with open(TOKEN_PATH) as f:
            data = json.load(f)
            expires_at = data.get("expiresAt", "unknown")
            return {
                "valid": True,
                "expires_at": expires_at,
                "path": str(TOKEN_PATH)
            }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "path": str(TOKEN_PATH)
        }

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║              Kiro API 反向代理服务器                           ║
╠══════════════════════════════════════════════════════════════╣
║  端口: 8000                                                   ║
║  OpenAI 兼容接口: http://127.0.0.1:8000/v1/chat/completions   ║
╠══════════════════════════════════════════════════════════════╣
║  使用方法:                                                    ║
║  curl http://127.0.0.1:8000/v1/chat/completions \\            ║
║    -H "Content-Type: application/json" \\                     ║
║    -d '{"model":"claude-sonnet-4","messages":[{"role":"user",║
║         "content":"Hello"}]}'                                 ║
╚══════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000)
