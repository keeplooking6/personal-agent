"""
B4 · 让模型自己用 Notion MCP 工具查笔记

运行：  python b4_mcp_query.py "我关于 XX 的笔记里写了什么"
        （不带参数时用一个默认问题）
该看到：模型自己决定调用 Notion 的搜索/读取工具，拿到真实笔记内容后作答。

这一关把 B2（模型自动调工具）和 B3（连 MCP）合起来，就是一个最小的「Agent」：
    模型思考 -> 决定调工具 -> 执行 MCP 工具 -> 结果回填 -> 模型继续，直到给出答案。
这正是现有 TS 项目 route.tsx 里做的事，只是这里用 Python 拆开给你看清楚。

阶段 1 增强：集成 observe.TraceLogger 输出结构化 trace。
"""

import asyncio
import json
import sys
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from common import MCP_TOKEN, MCP_URL, QWEN_MODEL, NO_THINKING, get_client
from observe import TraceLogger

client = get_client()

MAX_STEPS = 10  # 最多让模型来回调 5 步工具，防止无限循环


def mcp_tools_to_openai(mcp_tools) -> list:
    """把 MCP 的工具描述，翻译成模型能看懂的 OpenAI 工具格式。"""
    out = []
    print("-" * 40)
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
    """MCP 工具返回的内容可能有多段，这里把文字拼起来。"""
    parts = []
    for item in call_result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else "(无文本内容)"

async def select_relevant_tools(question: str, all_tools, client, max_tools=5) -> list:
    """根据用户问题，让 LLM 挑选最相关的工具名称，返回过滤后的工具列表"""

    # 构建简短的摘要，节省这次路由调用的 token
    summaries = "\n".join([f"- {t.name}: {t.description or '无描述'}" for t in all_tools])
    # print("summaries:",summaries)
    # 将工具的描述进行精简
    simple_prompt = f"""
        请将以下工具的错误码进行精简，例如把：
        Error Responses:
        400: Bad request
        403: The integration lacks the read/update content capability required for this page.       
        404: Page not found or not shared with the integration.
        409: Conflict (e.g. row limit exceeded).
        429: Rate limited.
        压缩成一行短句（Tips），放在描述末尾：
        Tips: Fails with 400(bad input), 403(no permission), 404(not found/shared), 409(conflict), 429(rate limit).
        可用工具列表有：
        {summaries}
    """
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": simple_prompt}],
        temperature=0.1,  # 极低温度，保证稳定输出 JSON
        extra_body=NO_THINKING
    )
    
    simple_summaries = resp.choices[0].message.content.strip()
    # print("summaries:",summaries)

    prompt = f"""用户问题：{question}

                请从以下 Notion 工具中，选出完成该任务**最必要**的工具名称（最多 {max_tools} 个）。
                只输出 JSON 数组格式，例如：["search", "query_database"]，不要包含其他任何文字。

                可用工具列表：
                {simple_summaries}
                """
    # 注意：这里调用时绝对不能带 tools 参数，否则模型会陷入“要不要调用”的混乱
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # 极低温度，保证稳定输出 JSON
        extra_body=NO_THINKING
    )
    
    raw = resp.choices[0].message.content.strip()
    try:
        # 去掉可能的 markdown 代码块标记
        if raw.startswith("```json"):
            raw = raw[7:-3]
        selected_names = json.loads(raw)
        print("selected_names:",selected_names)
        if not isinstance(selected_names, list):
            selected_names = []
    except:
        print("解析失败，降级为静态关键词匹配（保底）")
        # 如果解析失败，降级为静态关键词匹配（保底）
        keywords = ["search", "query", "page", "database", "block"]
        selected_names = [t.name for t in all_tools if any(k in t.name.lower() for k in keywords)]
    # 根据选出的名字过滤原始工具
    filtered = [t for t in all_tools if t.name in selected_names]
    return filtered if filtered else all_tools[:3]  # 如果空，给几个最通用的

async def run_agent(question: str, trace: TraceLogger | None = None) -> str:
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # 拿到全部工具，因为客户端连接了 Notion MCP 服务器
            mcp_tools = (await session.list_tools()).tools
                
            # 新增路由过滤
            relevant_tools = await select_relevant_tools(question, mcp_tools, client)
            tools = mcp_tools_to_openai(relevant_tools)  # 现在只传子集
            messages = [
                {"role": "system", "content": "你可以使用 Notion 工具查找用户的笔记。用中文简洁作答。"},
                {"role": "user", "content": question},
            ]

            for step in range(MAX_STEPS):
                start = time.time()
                resp = client.chat.completions.create(
                    model=QWEN_MODEL, messages=messages, tools=tools, extra_body=NO_THINKING
                )
                elapsed = time.time() - start
                if trace:
                    trace.log_llm(f"agent_step_{step + 1}", resp, elapsed, step=step + 1)

                msg = resp.choices[0].message

                if not msg.tool_calls:
                    return msg.content or ""

                messages.append(msg)
                for call in msg.tool_calls:
                    print("11111111111")
                    args = json.loads(call.function.arguments or "{}")
                    print("args:",args)
                    t0 = time.time()
                    result = await session.call_tool(call.function.name, arguments=args)
                    text = extract_text(result)
                    tool_elapsed = time.time() - t0
                    if trace:
                        print("22222222")
                        trace.log_tool(call.function.name, args, len(text), tool_elapsed)
                    else:
                        print(f"[第 {step + 1} 步] 调用工具 {call.function.name}，参数 {args}")
                        print(f"        工具返回（前 200 字）：{text[:200]}\n")
                    print("3333333")
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": text[:4000]}
                    )

    return "（达到最大步数仍未给出最终答案，可换个更明确的问题再试）"


async def main() -> None:
    print('sys.argv',sys.argv)
    question = sys.argv[1] if len(sys.argv) > 1 else "帮我搜索并总结我 Notion 中标题为“菜谱”的笔记。其链接为：https://www.notion.so/ae7e897a389c4887b57a7fff5b06b979?source=copy_link"
    trace = TraceLogger()
    answer = await run_agent(question, trace=trace)
    print("\nAI：", answer)
    # trace.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
