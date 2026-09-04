# Agent 入门闯关（Python 版）

这是一套「一个个能跑出结果的小脚本」，带你从零把个人 Agent 的核心能力玩一遍。
每个脚本只做一件事，`python 文件名.py` 就能看到结果。

## 成长路线图（面试导向）

完整递进路线见 [`docs/`](docs/) 目录：

| 阶段 | 文档 | 核心能力 |
|------|------|----------|
| 0 地基 | [stage0_agent_loop.md](docs/stage0_agent_loop.md) | Agent Loop |
| 1 Tool | [stage1_tool_cases.md](docs/stage1_tool_cases.md) | Tool Calling / MCP |
| 2 RAG | [stage2_rag_experiment.md](docs/stage2_rag_experiment.md) | 检索增强 + 调优 |
| 3 Memory | [stage3_memory_layers.md](docs/stage3_memory_layers.md) | 记忆分层 + 持久化 |
| 4 Planning | [stage4_plan_vs_workflow.md](docs/stage4_plan_vs_workflow.md) | Plan vs Workflow |
| 5 Eval | [stage5_observe_eval.md](docs/stage5_observe_eval.md) | 可观测 + 评估 |
| 6 整合 | [stage6_interview_narrative.md](docs/stage6_interview_narrative.md) | 架构 + 面试叙事 |

整合模块：
- [`agent_core.py`](agent_core.py) — 编排器（auto/chat/rag/tool 路由）
- [`observe.py`](observe.py) — 结构化 trace
- [`rag_core.py`](rag_core.py) / [`memory_store.py`](memory_store.py) — 可复用能力层
- [`j1_api.py`](j1_api.py) — FastAPI 服务入口

## 开始前（只做一次）

1. 装 Python 依赖（建议用虚拟环境）：

```bash
cd d:\ai\personal-agent
pip install -r requirements.txt
```

2. 配置：脚本自动读取 `d:\ai\notion-mcp-chat\.env` 或上级 `.env`（Qwen + MCP）。
   连 Notion 的关卡需要 MCP 服务在 `localhost:8000` 跑着。

3. 初始化 RAG 数据（示例笔记已放在 `data/notes.json`）：

```bash
# 先用 c2 打标签，再切块入库【将url取出单独存放、md格式去除】】
python c2_summarize.py
python c3_chunk.py
python d2_store_chroma.py
```

## 闯关顺序（一次只打一关，跑通再下一关）

### A 热身：先和模型说上话
- `python a1_talk.py` — 发一句话，打印回复（第一次跑通）
- `python a2_chat_loop.py` — 终端里连续聊天，体会「历史 = 记忆」
- `python a3_stream.py` — 逐字输出（打字机效果）

### B 工具调用：让模型会用工具
- `python b1_tool_manual.py` — 手动喂工具结果，看清「工具」本质
- `python b2_tool_auto.py` — 模型自己决定调用函数（function calling）
- `python b3_mcp_list_tools.py` — 连 Notion MCP，列出你有哪些工具
- `python b4_mcp_query.py "问题"` — 模型自己用 Notion 工具查笔记（最小 Agent，含 trace）

### C 数据接入：把笔记搬到本地
- `python c1_pull_notes.py` — 拉 Notion 笔记存 `data/notes.json`（连不上会用示例数据）
- `python c2_summarize.py` — LLM 给每篇笔记打标签（note_type/insight_type/summary/tags），生成 `data/notes_enriched.json`
- `python c3_chunk.py` — 把正文切成小块 `data/chunks.json`（优先读 enriched 数据，metadata 携带标签）
- `python c4_incremental.py` — 体会「只更新变化的」增量同步

### D RAG：让它读你的笔记回答
- `python d1_embedding.py` — 把文字变成向量，看它长啥样（首次会下小模型）
- `python d2_store_chroma.py` — 把块存进本地向量库 Chroma
- `python d3_retrieve.py "问题"` — 只检索，先确认找得准
- `python d4_rag_answer.py "问题"` — 检索 + 模型作答（带出处 + trace）

### E 记忆：让它记住你
- `python e1_summary.py` — 长对话压缩成摘要（省上下文）
- `python e2_memory.py` — 抽取「关于你」的事实存下来，下次启动还记得

### F 状态：存进数据库
- `python f1_sqlite.py` — 对话存 SQLite，重启续上（`--new` 开新会话，`--list` 看历史）

### G 规划与流程：先计划再执行
- `python g1_plan_execute.py "任务"` — 模型先出步骤计划，再逐步执行
- `python g2_workflow.py` — 固定流程：拉笔记→摘要→（确认后）写回 Notion

### H 观测与评估：看得见 + 能打分
- `python h1_observe.py` — 打印每次调用的耗时和 token
- `python h2_eval.py` — 对 20 条 eval 集自动打分（`--report docs/reports/baseline.json`）
- `python run_experiments.py` — chunk/top_k 参数对比实验

### I 多 Agent：两个角色配合
- `python i1_multi_agent.py` — 检索员 + 写作员配合写一份周报

### J 接回界面（可选，放最后）
- `uvicorn j1_api:app --reload --port 8010` — Agent 编排 API，访问 `/docs` 调试

## 每一关对应的「岗位能力」

- A/B → Tool Calling（工具调用）
- C → 数据接入 / 数据管道
- D → RAG（检索增强）
- E → Memory（记忆）
- F → 状态管理 / 持久化
- G → Planner + Workflow（规划与流程）
- H → 可观测性 + 评估（最容易被忽略、最加分的一环）
- I → 多 Agent 协作
- J → 服务化 / Orchestrator

## 卡住了怎么办

- 连不上 Qwen：检查 `notion-mcp-chat/.env` 里的 `QWEN_BASE_URL` 和服务是否开着。
- 连不上 Notion MCP：确认 `localhost:8000` 的 MCP 服务在跑；B/C/G 关才需要它。
- D 关首次慢：在下一个小向量模型，属正常，之后就快了。
- 工具调用/写入报参数错：不同 Notion MCP 工具命名和参数不同，先用 `b3` 看清工具说明再调整。

## 目录说明

- `common.py` — 共用配置和连模型的客户端
- `agent_core.py` — 编排器（chat/rag/tool 路由）
- `observe.py` / `rag_core.py` / `memory_store.py` / `pipeline.py` — 可复用模块
- `mcp_helper.py` — 连 Notion MCP 的小助手
- `data/` — 运行时数据（notes/chunks/向量库/记忆/数据库/eval 集）
- `docs/` — 成长路线文档
