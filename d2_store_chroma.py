"""
D2 · 把笔记块存进向量库 Chroma

运行：  python d2_store_chroma.py
前提：  先跑过 c3_chunk.py，已有 data/chunks.json。
该看到：打印存入了多少个块，并在 data/chroma/ 生成本地向量库。

Chroma 会自动帮你把每个块转成向量并存好（用的就是 D1 那个模型）。
你只管把「文字 + 编号 + 附加信息」丢进去，检索的事它全包了。

P1 增强：复用 pipeline.store_chroma，metadata 自动携带
note_type / insight_type / summary / tags，支持按类型过滤检索。
"""

import chromadb
from pathlib import Path

from pipeline import store_chroma, CHUNKS_FILE, CHROMA_DIR, COLLECTION


def main() -> None:
    if not CHUNKS_FILE.exists():
        print("没找到 chunks.json，请先运行 c1_pull_notes.py 和 c3_chunk.py")
        return

    count = store_chroma()

    # 打印分类统计，直观看 enrichment 是否生效
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION)
    all_meta = collection.get(include=["metadatas"])
    type_dist = {}
    for m in all_meta["metadatas"]:
        nt = m.get("note_type", "?")
        type_dist[nt] = type_dist.get(nt, 0) + 1

    print(f"已把 {count} 个块存入向量库：{CHROMA_DIR}")
    print(f"集合『{COLLECTION}』当前条数：{collection.count()}")
    print(f"分类分布：{type_dist}")


if __name__ == "__main__":
    main()
