"""
C1 · 把 Notion 笔记拉到本地，存成 notes.json

运行：  python c1_pull_notes.py
       python c1_pull_notes.py "搜索我的学习笔记"
该看到：终端打印拉到了多少条笔记，并生成 data/notes.json。

为什么要「拉到本地」：B4 是每次都实时问 Notion，慢且贵。做 RAG（D 关）需要
    先把笔记「一次性搬到本地」建索引。这就是「数据接入」里最常见的离线同步。

模型驱动：不再硬编码搜索词和获取逻辑（旧版用 NOTION_SEARCH_QUERY + 遍历块），
    而是由模型根据用户需求自主决定使用什么工具、如何获取内容、何时完成。
    如果连不上或找不到工具，会自动写入一份示例数据，保证后面 D 关照样能练。
"""

import argparse
import asyncio
import json
import traceback
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from common import MCP_TOKEN, MCP_URL, QWEN_MODEL, NO_THINKING, get_client

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
NOTES_FILE = DATA_DIR / "notes.json"

MAX_STEPS = 8

SAMPLE_NOTES = [
    {"id": "sample-1", "title": "学习笔记：什么是 RAG",
     "text": "RAG 是检索增强生成。先把资料切块存进向量库，提问时检索最相关的块，拼进提示词让模型据此回答，能减少幻觉。",
     "last_edited_time": "2026-07-01T10:00:00Z"},
    {"id": "sample-2", "title": "项目：notion-mcp-chat",
     "text": "一个用 Next.js + AI SDK 把本地 Qwen 模型和 Notion MCP 连起来的聊天项目，目标是做成个人 Agent。",
     "last_edited_time": "2026-07-02T09:30:00Z"},
    {"id": "sample-3", "title": "待办：本周学习计划",
     "text": "本周重点学习 Agent 的记忆和规划，先把 RAG 跑通，再做 Memory。",
     "last_edited_time": "2026-07-03T20:00:00Z"},
]


def _short_desc(tool) -> str:
    desc = tool.description or ""
    return desc.split("Error Responses")[0].strip() if "Error Responses" in desc else desc


def _simplify_schema(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    props = schema.get("properties", {})
    simple_props = {}
    for key, val in props.items():
        if not isinstance(val, dict):
            simple_props[key] = {}
            continue
        t = val.get("type", "string")
        if t == "object" and "properties" in val:
            sub = {}
            for sk, sv in val["properties"].items():
                sub[sk] = {"type": sv.get("type", "string") if isinstance(sv, dict) else "string"}
            simple_props[key] = {"type": "object", "properties": sub}
        elif isinstance(t, list):
            simple_props[key] = {"type": [x for x in t if isinstance(x, str)] or "string"}
        else:
            simple_props[key] = {"type": t}
    return {"type": "object", "properties": simple_props, "required": schema.get("required", [])}


def _tools_to_openai(mcp_tools: list) -> list:
    """把 MCP 的工具描述，翻译成模型能看懂的 OpenAI 工具格式。"""
    out = []
    for t in mcp_tools:
        out.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": _short_desc(t),
                "parameters": _simplify_schema(t.inputSchema) if t.inputSchema
                              else {"type": "object", "properties": {}},
            },
        })
    return out


def _extract_text(call_result) -> str:
    parts = []
    for item in call_result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else ""


def _parse_json_array(text: str) -> list | None:
    for marker in ("```json", "```"):
        if marker in text:
            text = text.split(marker, 1)[1]
            if "```" in text:
                text = text.split("```")[0]
            break
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


async def _llm(messages: list, tools: list | None = None) -> str | None:
    resp = await asyncio.to_thread(
        get_client().chat.completions.create,
        model=QWEN_MODEL, messages=messages, tools=tools, extra_body=NO_THINKING,
    )
    msg = resp.choices[0].message
    messages.append(msg.model_dump())
    return msg.content if not msg.tool_calls else None


async def _list_tools() -> list:
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return (await session.list_tools()).tools


async def _call_tool_raw(name: str, args: dict) -> str:
    """直接调用 MCP 工具、不经过 LLM，返回原始文本内容。"""
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments=args)
            return _extract_text(result)


async def pull_from_notion(user_query: str = "") -> list | None:
    client = get_client()

    # ── Phase 0: 列出工具 ──
    all_tools = await _list_tools()

    # ── Phase 1: 模型选择工具（不连 MCP） ──
    summary = "\n".join(f"- {t.name}: {_short_desc(t)}" for t in all_tools)
    sel = await _llm([
        {"role": "user", "content": (
            f"用户需求：{user_query or '搜索 Notion 中与 AI agent 相关的笔记，获取正文内容'}\n\n"
            f"可用工具：\n{summary}\n\n"
            "完成这个需求需要哪些工具？只输出 JSON 数组，如 [\"t1\",\"t2\"]，不要其他文字。"
        )},
    ])
    selected = []
    if sel:
        names = _parse_json_array(sel)
        if isinstance(names, list):
            selected = [t for t in all_tools if t.name in names]
    if not selected:
        print("  [选择] 模型未选出工具，降级使用全部工具")
        selected = all_tools
    print(f"  [选择] 模型已选 {len(selected)} 个工具，工具列表为：\n {selected}")

    # ── Phase 2: 浅层 agent 循环——只搜页面、不出完整内容 ──
    tool_defs = _tools_to_openai(selected)
    messages = [
        {"role": "system", "content": (
            "你是一个 Notion 笔记拉取助手。你的任务：\n"
            "1. 搜索 Notion 找到用户需要的笔记\n"
            "2. 使用 Notion 工具获取每条笔记的 ID 和标题\n"
            "3. 当你确定收集了所有需要的内容后，输出 JSON 数组"
            "，放在 ```json ... ``` 代码块中\n"
            "每条格式：{\"id\":\"...\",\"title\":\"...\",\"last_edited_time\":\"...\"}\n"
            "注意：不要输出 text 字段，内容稍后由系统自动填充。"
        )},
        {"role": "user", "content": user_query or "请搜索我的 Notion 中和 AI agent 相关的笔记。"},
    ]

    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            def _cull_context(msgs: list):
                """ 防止对话历史无限膨胀把模型上下文撑爆 """
                if len(msgs) <= 4: # 消息很少时不用裁
                    return
                keep = msgs[:2] # 保留前 2 条：system + 用户最初的需求
                tail = []
                for m in reversed(msgs[2:]): # 从末尾往前扫
                    tail.append(m)
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        break  # 扫到「最近一次发起工具调用的 assistant 消息」就停
                tail.reverse() # 恢复正序
                msgs[:] = keep + tail # 原地替换（不返回新列表）

            for step in range(MAX_STEPS):
                _cull_context(messages)
                try:
                    resp = await asyncio.to_thread(
                        client.chat.completions.create,
                        model=QWEN_MODEL, messages=messages, tools=tool_defs, extra_body=NO_THINKING,
                    )
                except Exception as e:
                    if "exceed_context_size_error" in str(e) or "BadRequestError" in type(e).__name__:
                        print(f"  [执行 {step + 1}] 上下文超限，跳过本轮")
                        break
                    else:
                        raise
                msg = resp.choices[0].message
                messages.append(msg.model_dump())

                if not msg.tool_calls:
                    print(f"  [执行 {step + 1}] 模型已完成")
                    break

                print(f"  [执行 {step + 1}] 调用了 {len(msg.tool_calls)} 个工具")
                for call in msg.tool_calls:
                    args = json.loads(call.function.arguments or "{}")
                    print(f"    → {call.function.name}")
                    try:
                        result = await session.call_tool(call.function.name, arguments=args)
                        text = _extract_text(result)
                    except Exception as tool_e:
                        print(f"      ⚠ 调用失败: {tool_e}")
                        text = f"(工具调用失败: {tool_e})"
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": text[:2000]}
                    )

    # ── Phase 3: 从最终回复提取页面列表 ──
    page_list = None
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") != "tool" and not m.get("tool_calls"):
            page_list = _parse_json_array(m.get("content", ""))
            if page_list:
                break
    if not page_list:
        return None

    # ── Phase 4: 直接调 MCP 拉取完整内容 ──
    print(f"  [获取] 共 {len(page_list)} 条笔记，正在获取全文 ...")
    for page in page_list:
        page_id = page.get("id", "")
        if not page_id:
            page["text"] = ""
            continue
        raw = await _call_tool_raw("API-retrieve-page-markdown", {"page_id": page_id})
        if raw:
            try:
                data = json.loads(raw)
                page["text"] = data.get("markdown", raw)[:20000]
            except json.JSONDecodeError:
                page["text"] = raw[:20000]
        else:
            blocks = await _call_tool_raw("API-get-block-children", {"block_id": page_id})
            page["text"] = blocks[:20000]

    return page_list


def main() -> None:
    parser = argparse.ArgumentParser(description="从 Notion 拉取笔记到本地")
    parser.add_argument("query", nargs="?", default="",
                        help="告诉模型你想拉什么笔记（默认：AI agent 相关笔记）")
    args = parser.parse_args()

    if args.query:
        print(f"用户需求：{args.query}")
    else:
        print("未指定需求，默认拉取 AI agent 相关笔记")

    try:
        notes = asyncio.run(pull_from_notion(args.query))
    except BaseException as e:
        print(f"从 Notion 拉取失败：{e}")
        traceback.print_exc()
        notes = None

    if notes is None:
        print("未从 Notion 拉到笔记，使用内置示例数据，保证后续关卡可练。")
        notes = SAMPLE_NOTES

    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(notes)} 条笔记，已保存到 {NOTES_FILE}")


if __name__ == "__main__":
    main()
