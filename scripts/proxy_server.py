#!/usr/bin/env python3
"""
Kiro IDE 反向代理测试服务器
用于测试是否能成功拦截和转发 Kiro 的 API 请求
"""

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import json
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kiro Reverse Proxy Test")

# 原始 Kiro API 地址（如果需要转发到真实服务器）
KIRO_API_BASE = "https://api.kiro.dev"

# 记录所有请求
request_log = []

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有进入的请求"""
    body = await request.body()
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "method": request.method,
        "url": str(request.url),
        "path": request.url.path,
        "headers": dict(request.headers),
        "body": body.decode('utf-8', errors='ignore')[:2000] if body else None
    }
    
    request_log.append(log_entry)
    logger.info(f"📥 {request.method} {request.url.path}")
    logger.info(f"   Headers: {dict(request.headers)}")
    if body:
        logger.info(f"   Body: {body.decode('utf-8', errors='ignore')[:500]}...")
    
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "message": "Kiro Proxy Server Running", "requests_logged": len(request_log)}

@app.get("/logs")
async def get_logs():
    """查看所有记录的请求"""
    return {"total": len(request_log), "requests": request_log[-50:]}

@app.get("/clear")
async def clear_logs():
    """清空日志"""
    request_log.clear()
    return {"message": "Logs cleared"}

# 模拟认证成功响应
@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def mock_auth(request: Request, path: str):
    """模拟认证端点"""
    logger.info(f"🔐 Auth request: {path}")
    return JSONResponse({
        "success": True,
        "token": "mock-token-for-testing",
        "expires_in": 3600
    })

# 模拟 AI 对话端点
@app.post("/v1/chat/completions")
async def mock_chat_completions(request: Request):
    """模拟 OpenAI 兼容的聊天接口"""
    body = await request.json()
    logger.info(f"💬 Chat request: {json.dumps(body, ensure_ascii=False)[:500]}")
    
    # 返回模拟响应
    return JSONResponse({
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": "kiro-proxy-test",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "🎉 反向代理测试成功！你的请求已被成功拦截。"
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    })

# 捕获所有其他请求
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
async def catch_all(request: Request, path: str):
    """捕获所有其他请求并记录"""
    body = await request.body()
    
    logger.info(f"🎯 Caught: {request.method} /{path}")
    
    return JSONResponse({
        "proxy_status": "intercepted",
        "method": request.method,
        "path": f"/{path}",
        "message": "请求已被反向代理捕获",
        "headers_received": dict(request.headers)
    })

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║           Kiro IDE 反向代理测试服务器                          ║
╠══════════════════════════════════════════════════════════════╣
║  端口: 8000                                                   ║
║  查看日志: http://127.0.0.1:8000/logs                         ║
║  清空日志: http://127.0.0.1:8000/clear                        ║
╠══════════════════════════════════════════════════════════════╣
║  使用方法:                                                    ║
║  1. 修改 Kiro 的 JS 源码，将 api.kiro.dev 替换为 127.0.0.1:8000 ║
║  2. 或者修改 /etc/hosts 添加: 127.0.0.1 api.kiro.dev          ║
║  3. 启动 Kiro，观察此终端的日志输出                             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000)
