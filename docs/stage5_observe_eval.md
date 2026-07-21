# 阶段 5 · 可观测性与评估

## Observability vs Evaluation

| | 可观测性（Observability） | 评估（Evaluation） |
|--|--------------------------|-------------------|
| **目的** | 运行时看清发生了什么 | 离线量化质量好不好 |
| **时机** | 每次请求 | 固定 eval 集批量跑 |
| **指标** | 耗时、token、tool 次数、trace | 1-5 分、平均分、分类得分 |
| **本项目** | [`observe.py`](../observe.py) TraceLogger | [`h2_eval.py`](../h2_eval.py) + eval_set.json |

**面试金句：** Trace 告诉你「慢在哪、调了几次 tool」；Eval 告诉你「改完 chunk 到底变好了没有」。

## Trace 集成点

| 模块 | trace 事件 |
|------|-----------|
| [`b4_mcp_query.py`](../b4_mcp_query.py) | llm/agent_step_N, tool/name |
| [`d4_rag_answer.py`](../d4_rag_answer.py) | retrieve, llm/rag_generate |
| [`agent_core.py`](../agent_core.py) | route, llm, tool, retrieve |

### Trace 输出示例

```
[trace req-1751856000] step 1 retrieve top_k=3 hits=3 0.12s
[trace req-1751856000] step 2 llm/rag_generate 2.05s tokens=890
[trace 汇总] steps=2 llm=1 tool=0 elapsed=2.17s
```

Trace 可导出 JSON：`trace.save("docs/reports/trace_sample.json")`

## Eval 集结构

[`data/eval_set.json`](../data/eval_set.json) — 20 条：

| 类别 | 数量 | 测什么 |
|------|------|--------|
| factual | 12 | 笔记里有明确答案 |
| summary | 5 | 需要综合多条笔记 |
| rejection | 3 | 应拒答（天气、股价等） |

## 生成 Baseline 报告

```bash
python c3_chunk.py
python d2_store_chroma.py
python h2_eval.py --top-k 3 --report docs/reports/baseline.json
```

报告字段：
- `average_score` — 总体平均分
- `by_category` — factual/summary/rejection 分项
- `results[]` — 每题得分和回答预览

## 对比实验

```bash
python run_experiments.py   # → docs/reports/rag_experiments.json
```

用 eval 数字支撑：「chunk 从 600 改 300，rejection 类从 3.0 提到 4.7」。

## 验收自检

- [ ] 能展示一次完整 trace（RAG 或 tool loop）
- [ ] 能区分 Observability 和 Evaluation
- [ ] 有 baseline.json 或 rag_experiments.json 数字

## 可选加分

接入 Langfuse / OpenTelemetry 把 TraceLogger 输出接到可视化平台——入门面试不必须。
