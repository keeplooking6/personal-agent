"""
RAG 核心模块：检索 + grounded 生成，供 d4/h2/agent_core 复用。
"""

from __future__ import annotations

import time
from pathlib import Path

import chromadb

from common import QWEN_MODEL, NO_THINKING, get_client
from observe import TraceLogger
from pipeline import get_embedding_function

DATA_DIR = Path(__file__).resolve().parent / "data"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION = "notes"

DEFAULT_TOP_K = 3

# 渲染进提示词的链接长度上限。索引里的 urls 是建库时写进去的，
# 万一索引是旧数据（曾经混进过 3000+ 字符的 S3 预签名链接），
# 这里兜一道，别让元数据把提示词挤爆 —— 本地模型上下文只有 8192。
MAX_URL_CHARS_IN_PROMPT = 300

RAG_SYSTEM = (
    "你是基于用户笔记回答问题的助手。只能依据下面提供的资料回答，"
    "资料中没有的内容就直说『笔记里没有相关信息』，不要编造。"
    "回答末尾用【出处：资料x】标注你用了哪几条。"
)


def retrieve(
    question: str,
    k: int = DEFAULT_TOP_K,
    trace: TraceLogger | None = None,
    note_type_filter: str | None = None,
    insight_type_filter: str | None = None,
):
    """检索笔记块。

    P1 新增：可通过 note_type_filter / insight_type_filter 按类型过滤检索范围。
    不传 filter 时检索全部笔记（向后兼容）。
    """
    start = time.time()
    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = chroma.get_collection(COLLECTION, embedding_function=get_embedding_function())

    # 构造 where 条件：支持按 note_type 和 insight_type 过滤
    where = None
    if note_type_filter or insight_type_filter:
        conditions = []
        if note_type_filter:
            conditions.append({"note_type": note_type_filter})
        if insight_type_filter:
            conditions.append({"insight_type": insight_type_filter})
        where = conditions[0] if len(conditions) == 1 else {"$and": conditions}

    query_kwargs = {"query_texts": [question], "n_results": k}
    if where:
        query_kwargs["where"] = where
    res = collection.query(**query_kwargs)

    docs, metas = res["documents"][0], res["metadatas"][0]
    elapsed = time.time() - start
    if trace:
        trace.log_retrieve(question, k, len(docs), elapsed)
    return docs, metas


def build_context(docs: list[str], metas: list[dict]) -> str:
    lines = []
    for i, (doc, meta) in enumerate(zip(docs, metas), 1):
        header = f"[资料{i}]（来自《{meta.get('title', '')}》）"
        urls = meta.get("urls", "") or ""
        if urls:
            if len(urls) > MAX_URL_CHARS_IN_PROMPT:
                urls = urls[:MAX_URL_CHARS_IN_PROMPT] + "…"
            header += f"\n   链接：{urls}"
        lines.append(f"{header}\n{doc}")
    return "\n".join(lines)


def rag_answer(
    question: str,
    k: int = DEFAULT_TOP_K,
    trace: TraceLogger | None = None,
    note_type_filter: str | None = None,
    insight_type_filter: str | None = None,
) -> dict:
    """返回 {answer, sources, context}。

    P1 新增：note_type_filter / insight_type_filter 可按类型过滤检索范围。
    """
    client = get_client()
    docs, metas = retrieve(
        question, k=k, trace=trace,
        note_type_filter=note_type_filter,
        insight_type_filter=insight_type_filter,
    )
    context = build_context(docs, metas)

    start = time.time()
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": RAG_SYSTEM},
            {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
        ],
        extra_body=NO_THINKING,
    )
    elapsed = time.time() - start
    if trace:
        trace.log_llm("rag_generate", resp, elapsed, question=question[:80])

    answer = resp.choices[0].message.content
    sources = [meta.get("title", "") for meta in metas]
    return {"answer": answer, "sources": sources, "context": context, "top_k": k}
