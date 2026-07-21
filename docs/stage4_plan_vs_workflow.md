# 阶段 4 · Planning vs Workflow + 安全设计

## Plan vs Workflow 决策表

| 场景 | 选型 | 脚本 | 理由 |
|------|------|------|------|
| 根据笔记写周报 | Plan + Multi-Agent | g1 + i1 | 步骤可变、只读、可分工 |
| 同步摘要写回 Notion | 确定性 Workflow + HITL | g2 | 有副作用、需审计、步骤固定 |
| 用户自由问答 | Agent Loop + RAG | b4 + d4 | 无需预先规划 |
| 准备面试分享大纲 | Plan-and-Execute | g1 | 目标模糊、步骤由 LLM 拆 |
| 实时查 Notion 某页 | Agent Loop + Tool | b4 | 需实时、工具驱动 |

## G1 vs G2 核心区别

| | G1 Plan-and-Execute | G2 确定性 Workflow |
|--|---------------------|-------------------|
| 步骤来源 | LLM 动态规划 | 代码写死 |
| 可控性 | 低 | 高 |
| 适用 | 开放任务 | 已知流程、有副作用 |
| 企业占比 | ~20% | ~80%（Workflow + LLM 节点） |

**面试金句：** 企业里大部分「Agent 流程」其实是 Workflow 里嵌 LLM 节点，不是让模型自由发挥。

## 安全设计：为什么 Agent 不应自动写 Notion

### 风险

1. **误写**：模型理解错意图，写入错误内容
2. **不可审计**：自由 Agent 的 tool 调用难以复现
3. **无回滚**：Notion 写入后撤销成本高

### 本项目的安全边界

| 操作类型 | 策略 | 实现 |
|----------|------|------|
| 读笔记（批量） | RAG 离线索引 | c→d |
| 读 Notion（实时） | Agent Loop，只读 tool | b4 |
| 写 Notion | **Workflow + HITL** | g2：`input("确认写回? y/N")` |
| Agent 步数 | **MAX_STEPS=5** | b4、route.tsx、agent_core |

### G2 安全闸门代码路径

[`g2_workflow.py`](../g2_workflow.py) 第 3 步：

1. 打印摘要预览
2. 等待用户输入 `y` 才调用 MCP 写工具
3. 默认 `N` 取消，不触碰 Notion

**面试话术：** 「Agent 可以规划和读，但写外部系统必须过人工确认——这是 HITL（Human-in-the-Loop）。」

## Plan-and-Execute vs ReAct

| 模式 | 本项目的体现 | 特点 |
|------|-------------|------|
| Plan-and-Execute | g1：先 JSON 步骤数组，再逐步执行 | 步骤可预见，适合分享/报告类任务 |
| ReAct | 未单独实现（b4 每步即时决策调 tool） | 每步 Thought→Action→Observation |

**取舍：** 个人 Agent 场景用 g1 讲清 Planning 即可；ReAct 已在 b4 的 tool loop 中体现。

## 验收自检

- [ ] 能回答「什么时候 Planner，什么时候 Workflow？」
- [ ] 能解释 g2 写操作为什么必须 HITL
- [ ] 能讲企业 80% 是 Workflow + LLM 节点

## 跑通命令

```bash
python g1_plan_execute.py "帮我准备 Agent 面试分享"
python g2_workflow.py   # 注意第 3 步确认闸门
```
