# 阶段 2 · RAG 调优实验

## RAG 全链路

```
sync (c1) → chunk (c2) → embed+store (d2) → retrieve (d3) → generate (d4)
                ↑
         增量同步 (c3) 只更新变化的页面
```

## 为什么要增量同步（C3）

企业 RAG 不是每次全量重建索引。记录 `last_edited_time` 后，只 sync 变更页面，节省 embedding 成本和 downtime。个人笔记量小时差异不大，但这是**正确的工程习惯**。

## 参数实验方法

```bash
# 1. 确保有笔记数据
python c1_pull_notes.py   # 或直接用 data/notes.json 示例

# 2. 跑对比实验（自动重建 chunk + chroma + eval）
python run_experiments.py
```

实验矩阵（[`run_experiments.py`](../run_experiments.py)）：

| 实验 | chunk_size | overlap | top_k | 预期 |
|------|-----------|---------|-------|------|
| A（默认） | 300 | 50 | 3 | baseline |
| B | 600 | 80 | 3 | 块更大，可能丢细节 |
| C | 300 | 50 | 5 | 召回更多，可能引入噪声 |

报告输出：`docs/reports/rag_experiments.json`

## 手动单组实验

```bash
python c3_chunk.py --chunk-size 300 --overlap 50
python d2_store_chroma.py
python h2_eval.py --top-k 3 --report docs/reports/baseline.json
```

## 面试一页纸模板

| 项目 | 值 |
|------|-----|
| 评估集 | 20 条（factual / summary / rejection） |
| Baseline | chunk=300, top_k=3, avg=___ |
| 实验 B | chunk=600, avg=___ |
| 结论 | 小块 + top_k=3 在拒答题上更稳 / ... |
| 防幻觉 | d4 prompt 要求出处 + rejection 类 eval |

## 验收自检

- [ ] 能讲清 sync → chunk → embed → retrieve → generate
- [ ] 能解释 C3 增量同步的价值
- [ ] 有 before/after eval 数字（跑完 run_experiments.py 后填入）
