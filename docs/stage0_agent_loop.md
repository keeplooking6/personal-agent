# 阶段 0 · Agent Loop 地基

## 30 秒口述版（面试开场）

> 我的 Personal Agent 核心是 **Agent Loop**：用户提问后，LLM 决定是直接回答还是调用 Tool；若调用 Tool，我们执行 MCP 工具、把结果回填 messages，再让 LLM 继续，直到给出最终答案。我用 `MAX_STEPS=5` 防止无限循环——这和生产里 `notion-mcp-chat` 的 `stepCountIs(5)` 是同一道安全阀。

## Agent Loop 流程图

```
User 提问
   ↓
LLM 推理（带 tools schema）
   ↓
有 tool_call? ──否──→ 输出最终答案
   │
  是
   ↓
执行 Tool（MCP / 本地函数）
   ↓
结果回填 messages
   ↓
步数 < MAX_STEPS? ──否──→ 停止并提示
   │
  是 → 回到 LLM
```

## Python vs TypeScript：同一 Loop，两种实现

| 维度 | Python [`b4_mcp_query.py`](../b4_mcp_query.py) | TS [`route.tsx`](../../notion-mcp-chat/app/api/chat/route.tsx) |
|------|-----------------------------------------------|----------------------------------------------------------------|
| Agent 循环 | 手写 `for step in range(MAX_STEPS)` | AI SDK `streamText` + `stopWhen: stepCountIs(5)` |
| Tool 来源 | MCP → `mcp_tools_to_openai()` | MCP → AI SDK `toolSet` |
| Tool 执行 | `session.call_tool(name, args)` | SDK 自动执行 |
| 流式输出 | 否（教学版同步打印） | 是（`toUIMessageStreamResponse`） |
| 观测 | [`observe.py`](../observe.py) TraceLogger | 可接 Langfuse（选修） |

**面试话术：** 我先在 Python 里手写 Loop 理解每一步，再在 Next.js 里用 AI SDK 做生产封装——我知道 SDK 背后在干什么，不是黑盒调用。

## 验收自检

- [ ] 能白板画出 `User → LLM → tool_call? → execute → loop → answer`
- [ ] 能解释 `MAX_STEPS=5` 是防 runaway agent，不是性能优化
- [ ] 能对比 b4 和 route.tsx 的异同

## 跑通命令

```bash
cd d:\ai\personal-agent
python a1_talk.py
python a2_chat_loop.py
python b4_mcp_query.py "我 Notion 里有什么笔记"
```

（B4 需要 Qwen + Notion MCP 在线；连不上 MCP 可先跑 A 关建立 Loop 概念。）
