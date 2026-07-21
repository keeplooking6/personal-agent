"""
MCP 小助手：把「连 Notion MCP、列工具、调工具」这些重复代码收到一处，
C 关和 G 关都能直接用，不用每次重写 async 连接样板。
"""

import asyncio

from mcp import ClientSession # 只知道怎么按MCP协议收发消息
from mcp.client.streamable_http import streamablehttp_client

from common import MCP_TOKEN, MCP_URL


def _extract_text(call_result) -> str:
    parts = []
    for item in call_result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


async def list_tools() -> list:
    """返回工具对象列表（每个有 .name / .description / .inputSchema）。"""
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    # 向MCP_URL发起http连接
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _): 
        # 在连接上创建MCP会话
        async with ClientSession(read, write) as session:
            # 客户端告诉服务端“我是谁，支持哪些协议版本”，服务端回“我是 Notion MCP，支持 MCP 协议版本”。
            # 客户端根据服务端回复，选择合适的协议版本。
            await session.initialize()
            return (await session.list_tools()).tools


async def call_tool(name: str, arguments: dict) -> str:
    """调用一个 MCP 工具，返回拼好的文本结果。"""
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments=arguments)
            return _extract_text(result)


async def find_tool_name(*keywords: str) -> str | None:
    """在所有工具里，找名字包含任一关键词的工具名（大小写不敏感）。
    因为不同 Notion MCP 版本工具命名不同（search / API-post-search 等），
    用关键词模糊匹配更稳。
    """
    tools = await list_tools()
    for t in tools:
        low = t.name.lower()
        if any(k.lower() in low for k in keywords):
            return t.name
    return None


def run(coro):
    """同步脚本里跑异步函数的小包装。"""
    return asyncio.run(coro)
