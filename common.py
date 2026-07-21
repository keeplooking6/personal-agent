"""
共用配置和小工具。每一关的脚本都从这里拿到「连你 Qwen 的客户端」，
不用每次都重复写连接代码。

它会自动读取项目根目录（learn 的上一级）的 .env 文件，
所以你不用再单独配置，直接复用现有项目的设置。
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 从环境变量读配置，读不到就用默认值（和现有项目保持一致）
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "")
QWEN_API_KEY = os.getenv("qwen_api_key", "")

# Notion MCP 服务（和现有项目 app/lib/mcp.tsx 里一致）
MCP_URL = os.getenv("MCP_URL", "")
MCP_TOKEN = os.getenv("MCP_TOKEN", "")


def get_client() -> OpenAI:
    """返回一个连到你 Qwen 的 OpenAI 兼容客户端。

    OpenAI 官方库能连任何「OpenAI 兼容」的服务，只要把 base_url 换成你的地址即可。
    """
    return OpenAI(base_url=QWEN_BASE_URL, api_key=QWEN_API_KEY)


# 关闭 Qwen3 的思考模式（简单对话更快）。这是 llama.cpp 的扩展参数。
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}
