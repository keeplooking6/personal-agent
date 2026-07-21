"""
D3 · 输入问题，检索出最相关的几个笔记块

运行：  python d3_retrieve.py "什么是 RAG"
        python d3_retrieve.py "如何面对焦虑" --note-type growth
        python d3_retrieve.py "如何面对焦虑" --note-type growth --insight-type dilemma
        （不带参数用默认问题）
前提：  先跑过 d2_store_chroma.py。
该看到：打印出和你问题最相关的 3 个块，以及它们的「距离」（越小越相关）。

P1 增强：支持 --note-type / --insight-type 按类型过滤检索范围，
让知识检索和成长型笔记检索走不同路径。
"""

import sys
from pathlib import Path

import chromadb

from pipeline import get_embedding_function

DATA_DIR = Path(__file__).resolve().parent / "data"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION = "notes"


def _parse_args(argv: list[str]) -> tuple[str, int, str | None, str | None]:
    """解析命令行参数：question, top_k, note_type_filter, insight_type_filter。"""
    question = "语义检索能力的技术原理是什么"
    top_k = 3
    note_type_filter = None
    insight_type_filter = None

    for i, arg in enumerate(argv):
        if arg == "--top-k" and i + 1 < len(argv):
            top_k = int(argv[i + 1])
        elif arg == "--note-type" and i + 1 < len(argv):
            note_type_filter = argv[i + 1]
        elif arg == "--insight-type" and i + 1 < len(argv):
            insight_type_filter = argv[i + 1]
        elif not arg.startswith("--"):
            question = arg

    return question, top_k, note_type_filter, insight_type_filter


def main() -> None:
    question, top_k, note_type_filter, insight_type_filter = _parse_args(sys.argv[1:])

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION, embedding_function=get_embedding_function())

    # 构造 where 条件
    where = None
    if note_type_filter or insight_type_filter:
        conditions = []
        if note_type_filter:
            conditions.append({"note_type": note_type_filter})
        if insight_type_filter:
            conditions.append({"insight_type": insight_type_filter})
        where = conditions[0] if len(conditions) == 1 else {"$and": conditions}

    query_kwargs = {"query_texts": [question], "n_results": top_k}
    print("query_kwargs",query_kwargs)
    if where:
        query_kwargs["where"] = where
    res = collection.query(**query_kwargs)

    filter_desc = ""
    if note_type_filter:
        filter_desc += f"｜note_type={note_type_filter}"
    if insight_type_filter:
        filter_desc += f"｜insight_type={insight_type_filter}"

    print(f"问题：{question}{filter_desc}\n")
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        print(f"[{i}] 距离 {dist:.4f}｜来自《{meta.get('title', '')}》"
              f"｜type={meta.get('note_type', '?')}/{meta.get('insight_type', '-')}")
        print(f"    {doc}\n")


if __name__ == "__main__":
    main()
