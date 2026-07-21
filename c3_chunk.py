"""
C2 · 把笔记正文切成小块（chunking）

运行：  python c3_chunk.py
前提：  先跑过 c1_pull_notes.py，已有 data/notes.json。
        如果跑过 c2_summarize.py（data/notes_enriched.json 存在），
        chunk metadata 会自动携带 note_type / insight_type / summary / tags。
该看到：打印切出了多少块，并生成 data/chunks.json。

为什么要切块：模型上下文有限，一整篇长笔记塞不下、也不精准。
    把它切成小块，检索时只取最相关的几块，又准又省。
    「怎么切」直接决定 RAG 效果好坏——这是 RAG 里最被低估的一步。

这里用最简单的「按固定长度 + 少量重叠」切。重叠是为了避免把一句话从中间切断。
"""

import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
NOTES_FILE = DATA_DIR / "notes.json"
ENRICHED_FILE = DATA_DIR / "notes_enriched.json"
CHUNKS_FILE = DATA_DIR / "chunks.json"

CHUNK_SIZE = 800
OVERLAP = 150


def main() -> None:
    chunk_size = CHUNK_SIZE
    overlap = OVERLAP
    if "--chunk-size" in sys.argv:
        idx = sys.argv.index("--chunk-size")
        chunk_size = int(sys.argv[idx + 1])
    if "--overlap" in sys.argv:
        idx = sys.argv.index("--overlap")
        overlap = int(sys.argv[idx + 1])

    if not NOTES_FILE.exists() and not ENRICHED_FILE.exists():
        print("没找到笔记文件，请先运行 c1_pull_notes.py")
        return

    from pipeline import build_chunks

    chunks = build_chunks(chunk_size=chunk_size, overlap=overlap)
    source = "notes_enriched.json" if ENRICHED_FILE.exists() else "notes.json"
    print(f"来源 {source} -> 切成 {len(chunks)} 个块")
    print(f"参数 chunk_size={chunk_size} overlap={overlap}，已保存到 {CHUNKS_FILE}")


if __name__ == "__main__":
    main()
