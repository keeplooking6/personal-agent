# 决策记录 #002：检索质量分析、管道顺序修正与增量同步 bug

**决策日期**：2026-07-18
**项目阶段**：数据管道（C 系列）重排 + RAG 质量评估
**触发问题**：`d3_retrieve.py "什么是 RAG"` 检索结果不相关；c4_summarize 与 c2_chunk 执行顺序错误

---

## 一、当时面临的困惑（记录原始疑问）

1. **管道执行顺序困惑**：c4_summarize 是后加的，放在 c2_chunk 之后还是之前？
2. **c2_chunk 数据源困惑**：应该读 notes.json 还是 notes_enriched.json？
3. **c3_incremental enriched 丢失困惑**：增量更新后，notes_enriched.json 的字段消失了，是否要重新跑 c4？
4. **文件编号困惑**：按执行顺序应该是 ①拉取 ②打标 ③切块 ④增量，但编号是 c1→c2→c3→c4，而 c4 打标实际应在 c2 切块之前
5. **检索不准困惑**：`d3_retrieve.py "什么是 RAG"` 返回的 top-3 结果语义都不太相关
6. **Markdown 语法处理困惑**：入库时还是展示时去掉？chunk size 是否太小？

---

## 二、关键认知演进（思考过程记录）

### 认知 1：pipeline.py 的设计已经超前

`pipeline.load_notes()` 优先读 `notes_enriched.json`，无则回退 `notes.json`，缺失字段兜底填充。所以 c2_chunk（→c3_chunk）实际上已经在读取 enriched 数据。**问题不是代码，是文档和命名没跟上。**

→ **结论**：改文档和文件名，不改 pipeline 逻辑。

### 认知 2：c3_incremental 的 enriched merge 是个 bug

原代码：
```python
enriched[i] = next((n for n in notes if n["id"] == e["id"]), e)
```

用 raw note 替换了 enriched entry，导致 `note_type`/`insight_type`/`summary`/`tags` 全部丢失。**这不是设计问题，是 bug。**

→ **结论**：改为先调用 `summarize_note()` 重新打标，再合并写入 enriched 文件。

### 认知 3：当前场景不需要 block 级增量

分析了 block 级增量的可行性：由于重叠切块（overlapping chunking）导致块边界由总字符数决定，中间任意 block 变化都会导致后续所有 chunk 边界漂移。**在几十篇笔记的规模下，整篇全量更新最可靠。**

→ **结论**：保持整篇级全量更新，不做 block 级增量。对应思考整理为 `docs/增量更新策略与面试问答.md`。

### 认知 4：检索不准的三个层次

| 层次 | 问题 | 影响程度 |
|------|------|----------|
| 嵌入模型 | `all-MiniLM-L6-v2` 是 384 维通用英文小模型，中文区分力弱 | 主因 |
| chunk size | 300 字符对中文太小，chunk 语义碎片化 | 次因 |
| 文本噪声 | markdown 残留语法（`<br>`、`<empty-block/>`）参与 embedding | 辅因 |

→ **结论**：优先级 ①换中文 embedding 模型 ②增大 chunk size 至 500-800 ③入库前 strip markdown。

### 认知 5：Markdown 语法应在入库时去掉，而非取出时

取出时去掉会导致：
- chunk 向量被噪声污染
- embedding 空间不一致（查询是干净文本，chunk 是带噪声文本）

正确流程：拉取 markdown → 清洗 → 切块 → embed → 存 Chroma。如需保留格式供显示，单独存原始 markdown。

---

## 三、决策结果

| 决策 | 方案 | 影响范围 |
|------|------|----------|
| 管道顺序 | c1 → c2_summarize → c3_chunk → c4_incremental | README、docs、文件名 |
| 文件名重编 | c4→c2_summarize, c2→c3_chunk, c3→c4_incremental | 9 个源文件 + 5 个文档 |
| enrichment 复用 | 提取 `summarize_note()` 到 `pipeline.py` | c4_summarize、c3_incremental |
| 增量策略 | 保持整篇全量，不做 block 级 | 当前不修改 |
| 检索优化 | 暂不实施，记录为后续方向 | 待定 |

---

## 四、后续待办

- [ ] 换中文 embedding 模型（如 `BAAI/bge-small-zh-v1.5`）
- [ ] 增大 chunk size 至 500-800
- [ ] 入库前 strip markdown / HTML 语法
- [ ] `d2_store_chroma.py` 改为 upsert 而非重建 collection

---

## 五、相关文件

- `pipeline.py` — 数据管道核心，含 `summarize_note()` / `build_chunks()` / `store_chroma()`
- `c2_summarize.py` — 笔记打标
- `c3_chunk.py` — 切块
- `c4_incremental.py` — 增量同步（含 enrichment 重新打标）
- `d2_store_chroma.py` — Chroma 入库
- `d3_retrieve.py` — 检索验证
- `docs/增量更新策略与面试问答.md` — 增量策略面试准备
