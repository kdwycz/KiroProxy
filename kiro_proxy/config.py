"""配置模块"""
from pathlib import Path

KIRO_API_URL = "https://q.us-east-1.amazonaws.com/generateAssistantResponse"
MODELS_URL = "https://q.us-east-1.amazonaws.com/ListAvailableModels"
TOKEN_PATH = Path.home() / ".aws/sso/cache/kiro-auth-token.json"

# 配额管理配置
QUOTA_COOLDOWN_SECONDS = 300  # 配额超限冷却时间（秒）

# web_search 工具配置（Kiro API 不支持 webSearchTool 格式，默认过滤）
WEB_SEARCH_ENABLED = False

# 模型映射（将外部模型名映射到 Kiro 支持的 5 个模型）
# Kiro 支持: auto, claude-sonnet-4, claude-sonnet-4.5, claude-haiku-4.5, claude-opus-4.5
MODEL_MAPPING = {
    # === Claude 4.6（Kiro 暂不支持，降级到 4.5） ===
    "claude-opus-4.6": "claude-opus-4.5",
    "claude-sonnet-4.6": "claude-sonnet-4.5",
    "claude-haiku-4-5-20251001": "claude-haiku-4.5",

    # === Claude 4.x 旧版名称 ===
    "claude-4-opus": "claude-opus-4.5",
    "claude-4-sonnet": "claude-sonnet-4",

    # === Claude 3.5（Claude Code 旧版别名） ===
    "claude-3-5-sonnet-20241022": "claude-sonnet-4",
    "claude-3-5-sonnet-latest": "claude-sonnet-4",
    "claude-3-5-sonnet": "claude-sonnet-4",
    "claude-3-5-haiku-20241022": "claude-haiku-4.5",
    "claude-3-5-haiku-latest": "claude-haiku-4.5",

    # === Claude 3（旧版） ===
    "claude-3-opus-20240229": "claude-opus-4.5",
    "claude-3-opus-latest": "claude-opus-4.5",
    "claude-3-sonnet-20240229": "claude-sonnet-4",
    "claude-3-haiku-20240307": "claude-haiku-4.5",

    # === OpenAI GPT-5.x（Codex CLI 当前默认系列） ===
    "gpt-5.4": "claude-opus-4.5",
    "gpt-5.3-codex": "claude-sonnet-4.5",
    "gpt-5.3-codex-spark": "claude-sonnet-4.5",
    "gpt-5.2": "claude-sonnet-4.5",
    "gpt-5.2-codex": "claude-sonnet-4.5",
    "gpt-5.1": "claude-sonnet-4.5",
    "gpt-5.1-codex": "claude-sonnet-4.5",
    "gpt-5.1-codex-max": "claude-opus-4.5",
    "gpt-5": "claude-sonnet-4",
    "gpt-5-codex": "claude-sonnet-4",
    "gpt-5-codex-mini": "claude-haiku-4.5",

    # === OpenAI GPT-4.1 ===
    "gpt-4.1": "claude-sonnet-4.5",
    "gpt-4.1-mini": "claude-sonnet-4",
    "gpt-4.1-nano": "claude-haiku-4.5",

    # === OpenAI o 系列（推理模型） ===
    "o4-mini": "claude-sonnet-4",
    "o4-mini-high": "claude-sonnet-4.5",
    "o3": "claude-opus-4.5",
    "o3-pro": "claude-opus-4.5",
    "o3-mini": "claude-sonnet-4",
    "o1": "claude-opus-4.5",
    "o1-preview": "claude-opus-4.5",
    "o1-mini": "claude-sonnet-4",

    # === OpenAI GPT-4o / 旧版 ===
    "gpt-4o": "claude-sonnet-4",
    "gpt-4o-mini": "claude-haiku-4.5",
    "gpt-4-turbo": "claude-sonnet-4",
    "gpt-4": "claude-sonnet-4",
    "gpt-3.5-turbo": "claude-haiku-4.5",

    # === Gemini 3.x ===
    "gemini-3.1-pro": "claude-opus-4.5",
    "gemini-3-flash": "claude-sonnet-4.5",
    "gemini-3.1-flash-lite": "claude-haiku-4.5",

    # === Gemini 2.5 ===
    "gemini-2.5-pro": "claude-sonnet-4.5",
    "gemini-2.5-pro-latest": "claude-sonnet-4.5",
    "gemini-2.5-flash": "claude-sonnet-4",
    "gemini-2.5-flash-lite": "claude-haiku-4.5",

    # === Gemini 2.0 / 1.5（旧版） ===
    "gemini-2.0-flash": "claude-sonnet-4",
    "gemini-2.0-flash-thinking": "claude-opus-4.5",
    "gemini-1.5-pro": "claude-sonnet-4.5",
    "gemini-1.5-flash": "claude-sonnet-4",

    # === 简短别名 ===
    "sonnet": "claude-sonnet-4",
    "haiku": "claude-haiku-4.5",
    "opus": "claude-opus-4.5",
    "opus-4.6": "claude-opus-4.5",
}

KIRO_MODELS = {"auto", "claude-sonnet-4.5", "claude-sonnet-4", "claude-haiku-4.5", "claude-opus-4.5"}

def map_model_name(model: str) -> str:
    """将外部模型名称映射到 Kiro 支持的名称"""
    if not model:
        return "claude-sonnet-4"
    if model in MODEL_MAPPING:
        return MODEL_MAPPING[model]
    if model in KIRO_MODELS:
        return model
    model_lower = model.lower()
    if "opus" in model_lower:
        return "claude-opus-4.5"
    if "haiku" in model_lower:
        return "claude-haiku-4.5"
    if "sonnet" in model_lower:
        return "claude-sonnet-4.5" if "4.5" in model_lower else "claude-sonnet-4"
    return "claude-sonnet-4"
