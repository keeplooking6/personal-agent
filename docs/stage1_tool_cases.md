# 阶段 1 · Tool 设计

## Tool 设计三原则

1. **Schema 清晰**：工具名、参数、描述让模型能正确选择（见 `b4` 的 `mcp_tools_to_openai`）
2. **幂等优先**：读操作可重复；写操作要有确认或幂等键
3. **写操作需确认**：Notion 写入走 G2 Workflow + HITL，不走自由 Agent Loop

## MCP Tool vs 不用 Tool：3 条对比案例

### 案例 1：「我 Notion 里最近一条笔记是什么？」

| 方式 | 路径 | 优点 | 缺点 |
|------|------|------|------|
| **不用 Tool** | 纯 LLM 对话 | 快、零依赖 | **幻觉**：模型不知道你的 Notion 内容 |
| **用 MCP Tool** | b4 Agent Loop | **Grounded**：真实查 Notion | 慢、每步消耗 token、依赖 MCP 在线 |

**结论：** 需要**实时、权威**的外部数据 → 必须用 Tool。

---

### 案例 2：「根据我所有笔记，总结我在学什么？」

| 方式 | 路径 | 优点 | 缺点 |
|------|------|------|------|
| **纯 MCP 多次搜索** | b4 循环查 | 数据最新 | 慢、贵、难覆盖全库 |
| **RAG（D4）** | 本地 Chroma 检索 | 快、可 eval、可离线 | 需先 sync（C 关），非实时 |

**结论：** **批量读、反复问** → 离线 sync + RAG；MCP Tool 留给实时查和写。

---

### 案例 3：「帮我把今天小结写进 Notion」

| 方式 | 路径 | 优点 | 缺点 |
|------|------|------|------|
| **自由 Agent 自动写** | b4 直接 call create | 省事 | **危险**：误写、难审计、面试负分 |
| **确定性 Workflow + HITL** | g2_workflow | 可控、可预览、可取消 | 步骤固定，灵活性低 |

**结论：** **有副作用的写操作** → Workflow + 人工确认，不用自由 Agent。

---

## Tool Schema 转换（面试常问）

MCP 工具描述 → OpenAI function calling 格式：

```python
# b4_mcp_query.py
{
    "type": "function",
    "function": {
        "name": t.name,
        "description": t.description,
        "parameters": t.inputSchema,
    },
}
```

AI SDK 侧由 `@ai-sdk/mcp` 自动完成同样映射。

## 结构化 Trace 示例

运行 `python b4_mcp_query.py "搜索 Agent 笔记"` 可看到：

```
[trace req-xxx] step 1 llm/agent_step 2.31s tokens=512
[trace req-xxx] step 2 tool/notion_search 0.85s result_chars=1204
[trace req-xxx] step 3 llm/agent_step 1.92s tokens=890
[trace 汇总] steps=3 llm=2 tool=1 elapsed=5.08s
```

## 验收自检

- [ ] 能解释 MCP 适合「实时读写」，不适合「批量读全库」
- [ ] 能讲 tool schema 从 MCP 到 OpenAI 的转换
- [ ] 能举 3 个 Tool vs 非 Tool 的场景并说明取舍
