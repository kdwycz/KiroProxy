#!/usr/bin/env python3
"""Kiro API 特性验证测试

通过 KiroProxy Anthropic 兼容接口验证以下 Kiro API 特性：
1. contextUsagePercentage — 原始响应中是否存在
2. web_search 工具兼容性 — webSearchTool vs 过滤 vs toolSpecification
3. Thinking 模式 — system prompt 注入 thinking 标签
4. 空 history 处理

使用方法：
    python tests/test_kiro_features.py [--proxy-url http://127.0.0.1:8080]
"""

import json
import sys
import time
import argparse
from typing import Optional

try:
    from curl_cffi import requests
except ImportError:
    import requests

PROXY_URL = "http://127.0.0.1:8080"
RESULTS = []


def log(msg: str, level: str = "INFO"):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def record(test_name: str, status: str, detail: str):
    """记录测试结果"""
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "⏭️"}.get(status, "❓")
    RESULTS.append({"name": test_name, "status": status, "detail": detail})
    log(f"{icon} [{test_name}] {status}: {detail}")


def call_anthropic(
    messages: list,
    system: str = "",
    tools: list = None,
    model: str = "claude-haiku-4.5",
    stream: bool = False,
    timeout: int = 120
) -> dict:
    """通过 KiroProxy 的 Anthropic 兼容接口发送请求"""
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 1024,
        "stream": stream,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    resp = requests.post(
        f"{PROXY_URL}/v1/messages",
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    return resp


# ═══════════════════════════════════════════════════
# Test 1: contextUsagePercentage
# ═══════════════════════════════════════════════════

def test_context_usage_percentage():
    """验证 Kiro 原始响应是否包含 contextUsagePercentage

    策略：使用流式请求，KiroProxy 在流式模式下会逐 chunk 解析二进制响应。
    我们在 streaming SSE 的原始 bytes 中搜索 contextUsagePercentage 关键字。
    如果 KiroProxy 在流式模式下暴露了这个字段（即使它目前没有用到），
    我们可以在内部的二进制 payload 中找到它。

    实际上更可靠的方法：发送非流式请求，然后检查 KiroProxy server logs。
    但我们也可以发送流式请求，在 event-stream 中寻找线索。
    """
    test_name = "contextUsagePercentage"
    log(f"--- Test 1: {test_name} ---")

    # 方法1：非流式请求 - 检查 KiroProxy 返回的 usage 字段
    try:
        resp = call_anthropic(
            messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
            model="claude-haiku-4.5",
            stream=False,
        )

        if resp.status_code != 200:
            record(test_name, "FAIL", f"非流式请求失败 HTTP {resp.status_code}: {resp.text[:200]}")
            return

        data = resp.json()
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        log(f"非流式 usage: input={input_tokens}, output={output_tokens}")

        # 检查 token 是否为硬编码的 100（说明没有真实计算）
        if input_tokens == 100 and output_tokens == 100:
            log("Token counts 都是 100 — 当前为硬编码值")
        
    except Exception as e:
        record(test_name, "FAIL", f"非流式请求异常: {e}")
        return

    # 方法2：流式请求 - 搜索原始响应中的 contextUsagePercentage
    try:
        resp = call_anthropic(
            messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
            model="claude-haiku-4.5",
            stream=True,
        )

        if resp.status_code != 200:
            record(test_name, "FAIL", f"流式请求失败 HTTP {resp.status_code}")
            return

        raw_text = resp.text
        found = "contextUsagePercentage" in raw_text

        if found:
            # 尝试提取具体值
            import re
            match = re.search(r'contextUsagePercentage["\s:]+(\d+\.?\d*)', raw_text)
            value = match.group(1) if match else "unknown"
            record(test_name, "PASS", f"流式响应中检测到 contextUsagePercentage={value}")
        else:
            # 即使在流式 SSE 中没找到也不意味着 API 不返回
            # 因为 KiroProxy 会先解析 binary，再转成 SSE
            record(test_name, "WARN",
                   "流式 SSE 输出中未检测到 contextUsagePercentage — "
                   "需要在 providers/kiro.py parse_response() 内部捕获。"
                   f" 当前 usage 为硬编码 input={input_tokens}/output={output_tokens}")

    except Exception as e:
        record(test_name, "FAIL", f"流式请求异常: {e}")


# ═══════════════════════════════════════════════════
# Test 2: web_search 工具
# ═══════════════════════════════════════════════════

def test_web_search_tool():
    """验证 web_search 工具的不同传递方式"""
    test_name = "web_search"
    log(f"--- Test 2: {test_name} ---")

    base_messages = [{"role": "user", "content": "What is the current weather in Tokyo? Please use the web_search tool."}]

    # 一个普通的非 web_search 工具，确保基线正常
    normal_tool = {
        "name": "get_time",
        "description": "Get current time",
        "input_schema": {"type": "object", "properties": {"timezone": {"type": "string"}}}
    }

    # Test 2a: 不包含 web_search 工具（只有普通工具）— 应该正常
    log("2a: 只有普通工具（无 web_search）...")
    try:
        resp = call_anthropic(
            messages=base_messages,
            tools=[normal_tool],
            model="claude-haiku-4.5",
        )
        status_a = resp.status_code
        log(f"2a 结果: HTTP {status_a}")
        if status_a != 200:
            log(f"2a 响应: {resp.text[:300]}", "WARN")
    except Exception as e:
        status_a = -1
        log(f"2a 异常: {e}", "ERROR")

    # Test 2b: 包含 web_search 工具（Anthropic 格式）
    # KiroProxy 当前会将其转为 webSearchTool 格式
    log("2b: 包含 web_search 工具（Anthropic 原始格式）...")
    web_search_tool = {
        "name": "web_search",
        "description": "Search the web for information",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"]
        }
    }
    try:
        resp = call_anthropic(
            messages=base_messages,
            tools=[normal_tool, web_search_tool],
            model="claude-haiku-4.5",
        )
        status_b = resp.status_code
        log(f"2b 结果: HTTP {status_b}")
        if status_b != 200:
            log(f"2b 响应: {resp.text[:300]}", "WARN")
    except Exception as e:
        status_b = -1
        log(f"2b 异常: {e}", "ERROR")

    # Test 2c: 使用 web_search_20250305 名称
    log("2c: 使用 web_search_20250305 名称...")
    ws_tool_2 = {
        "name": "web_search_20250305",
        "description": "Search the web",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}
    }
    try:
        resp = call_anthropic(
            messages=base_messages,
            tools=[normal_tool, ws_tool_2],
            model="claude-haiku-4.5",
        )
        status_c = resp.status_code
        log(f"2c 结果: HTTP {status_c}")
        if status_c != 200:
            log(f"2c 响应: {resp.text[:300]}", "WARN")
    except Exception as e:
        status_c = -1
        log(f"2c 异常: {e}", "ERROR")
    
    # 分析结果
    if status_a == 200 and status_b != 200:
        record(test_name, "PASS",
               f"web_search 导致 {status_b} 错误 — 应该过滤掉而非转为 webSearchTool。"
               f" 无 web_search: {status_a}, 有 web_search: {status_b}, web_search_20250305: {status_c}")
    elif status_a == 200 and status_b == 200:
        record(test_name, "PASS",
               f"web_search 转换成功（webSearchTool 格式可用）。"
               f" 无 web_search: {status_a}, 有 web_search: {status_b}, web_search_20250305: {status_c}")
    else:
        record(test_name, "WARN",
               f"结果不确定。无 web_search: {status_a}, 有 web_search: {status_b}, web_search_20250305: {status_c}")


# ═══════════════════════════════════════════════════
# Test 3: Thinking 模式
# ═══════════════════════════════════════════════════

def test_thinking_mode():
    """验证 system prompt 注入 thinking 标签是否能触发思考模式"""
    test_name = "thinking_mode"
    log(f"--- Test 3: {test_name} ---")

    thinking_system = (
        "<thinking_mode>enabled</thinking_mode>"
        "<max_thinking_length>10000</max_thinking_length>\n\n"
        "You are a helpful assistant. Always think step by step before answering."
    )
    normal_system = "You are a helpful assistant."

    # 需要一个稍微需要推理的问题
    messages = [{"role": "user", "content": "What is 17 * 23? Show your reasoning."}]

    # Test 3a: 带 thinking 标签的请求
    log("3a: 带 thinking_mode 标签...")
    thinking_content = ""
    try:
        resp = call_anthropic(
            messages=messages,
            system=thinking_system,
            model="claude-sonnet-4",  # 使用更强的模型
        )

        if resp.status_code != 200:
            record(test_name, "FAIL", f"带 thinking 请求失败 HTTP {resp.status_code}: {resp.text[:200]}")
            return

        data = resp.json()
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                thinking_content += block.get("text", "")

        log(f"3a 响应长度: {len(thinking_content)} chars")
        log(f"3a 响应前 500 字符: {thinking_content[:500]}")
        
        has_thinking_tag = "<thinking>" in thinking_content
        
    except Exception as e:
        record(test_name, "FAIL", f"带 thinking 请求异常: {e}")
        return

    # Test 3b: 不带 thinking 标签的请求（对照组）
    log("3b: 不带 thinking_mode 标签（对照组）...")
    normal_content = ""
    try:
        resp = call_anthropic(
            messages=messages,
            system=normal_system,
            model="claude-sonnet-4",
        )

        if resp.status_code == 200:
            data = resp.json()
            content_blocks = data.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    normal_content += block.get("text", "")
            log(f"3b 响应长度: {len(normal_content)} chars")

        has_normal_thinking = "<thinking>" in normal_content

    except Exception as e:
        log(f"3b 对照组异常（可忽略）: {e}", "WARN")
        has_normal_thinking = False

    # 分析
    if has_thinking_tag and not has_normal_thinking:
        record(test_name, "PASS",
               f"thinking 模式有效！带标签时响应包含 <thinking> 块。"
               f" 带标签: {len(thinking_content)} chars, 无标签: {len(normal_content)} chars")
    elif has_thinking_tag and has_normal_thinking:
        record(test_name, "WARN",
               "两种情况都包含 <thinking> — 可能模型自带思考，不一定是标签触发的")
    elif not has_thinking_tag:
        # 进一步检查：即使没有 <thinking> 标签，响应是否明显更长（暗示有内部思考被剥离）
        len_diff = len(thinking_content) - len(normal_content)
        detail = (
            f"响应中未检测到 <thinking> 标签。"
            f" 带标签: {len(thinking_content)} chars, 无标签: {len(normal_content)} chars"
            f" (差异: {len_diff:+d} chars)"
        )
        if len_diff > 500:
            record(test_name, "WARN",
                   detail + " — 响应显著更长，可能有内部思考但未通过标签输出")
        else:
            record(test_name, "FAIL", detail)


# ═══════════════════════════════════════════════════
# Test 4: Thinking 模式（流式 - 更容易检测）
# ═══════════════════════════════════════════════════

def test_thinking_mode_stream():
    """使用流式请求验证 thinking 模式 — 在原始 SSE 中更容易检测到 thinking 标签"""
    test_name = "thinking_mode_stream"
    log(f"--- Test 4: {test_name} ---")

    thinking_system = (
        "<thinking_mode>enabled</thinking_mode>"
        "<max_thinking_length>10000</max_thinking_length>\n\n"
        "You are a helpful assistant."
    )

    messages = [{"role": "user", "content": "What is 17 * 23? Think step by step."}]

    try:
        resp = call_anthropic(
            messages=messages,
            system=thinking_system,
            model="claude-sonnet-4",
            stream=True,
        )

        if resp.status_code != 200:
            record(test_name, "FAIL", f"流式 thinking 请求失败 HTTP {resp.status_code}")
            return

        raw = resp.text
        has_thinking = "<thinking>" in raw
        has_thinking_end = "</thinking>" in raw

        # 提取 thinking 内容
        if has_thinking and has_thinking_end:
            import re
            match = re.search(r'<thinking>(.*?)</thinking>', raw, re.DOTALL)
            thinking_text = match.group(1)[:200] if match else "(无法提取)"
            record(test_name, "PASS",
                   f"流式响应包含 thinking 块！前 200 字符: {thinking_text}")
        elif has_thinking:
            record(test_name, "WARN",
                   "检测到 <thinking> 开始标签但未找到结束标签 — 可能被截断")
        else:
            record(test_name, "FAIL",
                   f"流式响应未检测到 <thinking> 标签 (响应长度: {len(raw)} chars)")

    except Exception as e:
        record(test_name, "FAIL", f"流式 thinking 请求异常: {e}")


# ═══════════════════════════════════════════════════
# Test 5: adaptive thinking mode
# ═══════════════════════════════════════════════════

def test_thinking_adaptive():
    """验证 adaptive thinking 模式"""
    test_name = "thinking_adaptive"
    log(f"--- Test 5: {test_name} ---")

    adaptive_system = (
        "<thinking_mode>adaptive</thinking_mode>"
        "<thinking_effort>high</thinking_effort>\n\n"
        "You are a helpful assistant."
    )

    messages = [{"role": "user", "content": "Solve: If 3x + 7 = 22, what is x?"}]

    try:
        resp = call_anthropic(
            messages=messages,
            system=adaptive_system,
            model="claude-sonnet-4",
            stream=True,
        )

        if resp.status_code != 200:
            record(test_name, "FAIL", f"adaptive thinking 请求失败 HTTP {resp.status_code}")
            return

        raw = resp.text
        has_thinking = "<thinking>" in raw

        if has_thinking:
            record(test_name, "PASS", "adaptive thinking 模式有效 — 响应包含 <thinking> 块")
        else:
            record(test_name, "WARN",
                   "adaptive 模式下未检测到 <thinking> — 模型可能认为问题太简单不需要思考")

    except Exception as e:
        record(test_name, "FAIL", f"adaptive thinking 请求异常: {e}")


# ═══════════════════════════════════════════════════
# Test 6: 基础连通性与 token 验证
# ═══════════════════════════════════════════════════

def test_basic_connectivity():
    """验证基本连通性"""
    test_name = "basic_connectivity"
    log(f"--- Test 0: {test_name} ---")

    try:
        resp = requests.get(f"{PROXY_URL}/v1/models", timeout=10)
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            model_ids = [m["id"] for m in models]
            record(test_name, "PASS", f"连接成功，{len(models)} 个模型: {', '.join(model_ids[:5])}")
            return True
        else:
            record(test_name, "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        record(test_name, "FAIL", f"连接失败: {e}")
        return False


def test_simple_chat():
    """验证基本聊天功能"""
    test_name = "simple_chat"
    log(f"--- Test 0b: {test_name} ---")

    try:
        resp = call_anthropic(
            messages=[{"role": "user", "content": "Say 'test ok' and nothing else."}],
            model="claude-haiku-4.5",
        )

        if resp.status_code == 200:
            data = resp.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            record(test_name, "PASS", f"聊天正常，AI 回复: {text[:100]}")
            return True
        else:
            record(test_name, "FAIL", f"HTTP {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as e:
        record(test_name, "FAIL", f"聊天请求异常: {e}")
        return False


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def print_summary():
    print("\n" + "=" * 70)
    print("  测试结果汇总")
    print("=" * 70)

    for r in RESULTS:
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "⏭️"}.get(r["status"], "❓")
        print(f"  {icon} {r['name']:30s} {r['status']:6s} — {r['detail'][:80]}")

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    warned = sum(1 for r in RESULTS if r["status"] == "WARN")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")

    print(f"\n  总计: {total} | ✅ {passed} | ⚠️ {warned} | ❌ {failed}")
    print("=" * 70)

    # 可落地改进建议
    print("\n📋 可落地改进建议：")
    for r in RESULTS:
        if r["status"] in ("PASS", "WARN"):
            if "contextUsagePercentage" in r["name"]:
                print("  → 在 parse_response() 中捕获 contextUsagePercentage 用于精确 token 统计")
            elif "web_search" in r["name"]:
                if "过滤" in r["detail"]:
                    print("  → web_search 工具应直接过滤，不要转为 webSearchTool 格式")
                else:
                    print("  → webSearchTool 格式可用，当前实现正确")
            elif "thinking" in r["name"]:
                if r["status"] == "PASS":
                    print("  → 实现 thinking 模式转换：将 Anthropic 的 thinking 参数转为 system prompt 前缀")


def main():
    parser = argparse.ArgumentParser(description="Kiro API 特性验证测试")
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8080", help="KiroProxy URL")
    args = parser.parse_args()

    global PROXY_URL
    PROXY_URL = args.proxy_url

    print("=" * 70)
    print(f"  Kiro API 特性验证测试")
    print(f"  代理地址: {PROXY_URL}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")

    # 前置检查
    if not test_basic_connectivity():
        print("\n❌ 无法连接 KiroProxy，中止测试。")
        sys.exit(1)

    if not test_simple_chat():
        print("\n❌ 基本聊天功能不可用，中止测试。")
        sys.exit(1)

    print()

    # 正式测试
    test_context_usage_percentage()
    print()
    test_web_search_tool()
    print()
    test_thinking_mode()
    print()
    test_thinking_mode_stream()
    print()
    test_thinking_adaptive()

    # 汇总
    print_summary()


if __name__ == "__main__":
    main()
