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

### G2 第 3 步：三层「谁决定什么」

「流程写死」不等于「工具选择也交给模型」。这三层要分清，否则一句「工具选择全交给模型」会被追问「那你 prompt 里为什么点名了两个工具」：

| 层 | 决定者 | 实现 |
|----|--------|------|
| 工具能力面 | **代码收窄** | `WRITE_TOOLS` 只声明 search + create，服务器上其余 notion 工具不暴露给模型；授权面就是能力面 |
| 流程与顺序 | **prompt 固化** | system prompt 点名两个工具 + 「先搜索、后创建」；这是自然语言软约束，代码里**没有**硬编码任何一次工具调用，也没传 `tool_choice="required"` |
| 调用与参数 | **模型生成** | 代码只做通用分发 `call_tool(name, args)` + 结果回填；唯一的工具专属逻辑是 post-page 的本地参数校验与成功判定 |

**模型真正不可替代的地方：** 参数依赖运行时数据——父页面 id 只存在于搜索结果里，摘要怎么拆成段落块也得现场生成，这些在开发期写不出来。所以这一步是「LLM 参数生成节点」，不是「LLM 决策节点」。

**面试话术：** 「写回这一步我只把两件事交给模型：生成调用和参数。工具面是我在代码里收窄的，顺序是我在 prompt 里固化的——所以每一次写操作是怎么被约束住的，我都说得出来。」

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
- [ ] 能讲清 G2 第 3 步三层分工（工具面/顺序/参数各归谁）

## 跑通命令

```bash
python g1_plan_execute.py "帮我准备 Agent 面试分享"
python g2_workflow.py   # 注意第 3 步确认闸门
```
