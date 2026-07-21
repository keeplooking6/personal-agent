"""
Personal Knowledge Agent 核心编排器。

路由策略（面试用）：
  - chat:  简单对话 + 长期记忆注入
  - rag:   本地笔记检索问答（读）
  - tool:  MCP Agent Loop（实时查 Notion）
  - auto:  关键词启发式路由（可替换为 LLM router）
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from common import MCP_TOKEN, MCP_URL, QWEN_MODEL, NO_THINKING, get_client
from memory_store import build_memory_system_prompt, load_memory
from observe import TraceLogger
from rag_core import rag_answer

MAX_STEPS = 5

RAG_KEYWORDS = ("笔记", "rag", "总结", "区别", "我的", "学过", "记过")
TOOL_KEYWORDS = ("notion", "mcp", "写进", "创建", "新建", "搜索notion", "查找页面")


def mcp_tools_to_openai(mcp_tools) -> list:
    out = []
    for t in mcp_tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def extract_text(call_result) -> str:
    parts = []
    for item in call_result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else "(无文本内容)"


def detect_route(message: str, mode: str = "auto") -> str:
    # 路由优先级：显式写入/创建动作 → tool；笔记检索 → rag；兜底 → rag
    # 本 agent 核心是读取用户笔记，因此大多数问题应先走 RAG。
    if mode != "auto":
        return mode
    lower = message.lower()
    # 仅显式写入/创建动作走 MCP tool（notion/mcp/写进/创建/新建），
    # 不再把宽泛的“搜索/查找”算作 tool，避免“查找笔记”被误路由到 MCP。
    if any(k in lower for k in ("notion", "mcp")) or any(
        k in message for k in ("写进", "创建", "新建")
    ):
        return "tool"
    # 笔记检索关键词走 RAG
    if any(k in lower for k in RAG_KEYWORDS) or any(k in message for k in RAG_KEYWORDS):
        return "rag"
    # 兜底走 rag：本 agent 以笔记阅读为核心，未知问题也优先查笔记
    return "rag"


class AgentCore:
    def __init__(self) -> None:
        self.client = get_client()

    def chat(self, message: str, trace: TraceLogger | None = None) -> dict[str, Any]:
        system = build_memory_system_prompt()
        start = time.time()
        resp = self.client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            extra_body=NO_THINKING,
        )
        elapsed = time.time() - start
        if trace:
            trace.log_llm("chat", resp, elapsed)
        return {
            "mode": "chat",
            "answer": resp.choices[0].message.content,
            "memory_facts": load_memory(),
        }

    def ask_rag(self, question: str, top_k: int = 3, trace: TraceLogger | None = None) -> dict[str, Any]:
        result = rag_answer(question, k=top_k, trace=trace)
        return {"mode": "rag", **result}

    async def ask_tool(self, question: str, trace: TraceLogger | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
        messages = [
            {
                "role": "system",
                "content": build_memory_system_prompt("你可以使用 Notion 工具。用中文简洁作答。"),
            },
            {"role": "user", "content": question},
        ]

        async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_tools = (await session.list_tools()).tools
                tools = mcp_tools_to_openai(mcp_tools)

                for step in range(MAX_STEPS):
                    start = time.time()
                    resp = self.client.chat.completions.create(
                        model=QWEN_MODEL, messages=messages, tools=tools, extra_body=NO_THINKING
                    )
                    elapsed = time.time() - start
                    if trace:
                        trace.log_llm(f"agent_step_{step + 1}", resp, elapsed)

                    msg = resp.choices[0].message
                    if not msg.tool_calls:
                        return {"mode": "tool", "answer": msg.content, "steps": step + 1}

                    messages.append(msg)
                    for call in msg.tool_calls:
                        args = json.loads(call.function.arguments or "{}")
                        t0 = time.time()
                        result = await session.call_tool(call.function.name, arguments=args)
                        text = extract_text(result)
                        if trace:
                            trace.log_tool(call.function.name, args, len(text), time.time() - t0)
                        messages.append(
                            {"role": "tool", "tool_call_id": call.id, "content": text[:4000]}
                        )

        return {
            "mode": "tool",
            "answer": "达到最大步数仍未给出最终答案，请换更明确的问题。",
            "steps": MAX_STEPS,
        }

    async def run(
        self,
        message: str,
        mode: str = "auto",
        top_k: int = 3,
        trace: TraceLogger | None = None,
    ) -> dict[str, Any]:
        route = detect_route(message, mode)
        if trace:
            trace.log_route(route, f"mode={mode}")

        if route == "rag":
            return self.ask_rag(message, top_k=top_k, trace=trace)
        if route == "tool":
            return await self.ask_tool(message, trace=trace)
        return self.chat(message, trace=trace)


def run_sync(message: str, mode: str = "auto", top_k: int = 3) -> dict[str, Any]:
    trace = TraceLogger()
    core = AgentCore()
    result = asyncio.run(core.run(message, mode=mode, top_k=top_k, trace=trace))
    trace.print_summary()
    result["trace"] = trace.summary()
    return result
