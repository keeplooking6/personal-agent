"""
I1 · 多 Agent 协作：检索员 + 写作员，配合写一份周报

运行：  python i1_multi_agent.py
前提：  先跑过 d2_store_chroma.py（检索员要用向量库）。
该看到：检索员先从你的笔记里找素材，写作员再据此写成一段周报，最后打印成品。

什么是多 Agent：把一个大任务拆给几个「各有专长」的角色分工。
    这里最简单的两个角色：
      - 检索员：只负责从笔记里找相关内容（用 RAG）
      - 写作员：只负责把素材组织成通顺的周报
    一个「协调者」把它们串起来。

重要认知：多 Agent 不总是更好——更慢、更贵、更难调。
    只有当「分工确实带来收益」时才值得用。这一关先建立直觉。
"""

from pathlib import Path

import chromadb

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION = "notes"


def retriever_agent(topic: str) -> str:
    """检索员：从向量库里找和主题相关的笔记片段。"""
    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = chroma.get_collection(COLLECTION)
    docs = collection.query(query_texts=[topic], n_results=5)["documents"][0]
    material = "\n".join(f"- {d}" for d in docs)
    print("【检索员】找到以下素材：")
    print(material, "\n")
    return material


def writer_agent(topic: str, material: str) -> str:
    """写作员：只根据检索员给的素材，写成一段周报。"""
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": "你是写作员。只根据提供的素材，写一段简洁的中文周报，分点罗列。"},
            {"role": "user", "content": f"主题：{topic}\n素材：\n{material}"},
        ],
        extra_body=NO_THINKING,
    )
    return resp.choices[0].message.content


def orchestrator(topic: str) -> None:
    """协调者：安排检索员 -> 写作员的流水，串起整个任务。"""
    print(f"【协调者】任务：写一份关于「{topic}」的周报\n")
    material = retriever_agent(topic)
    report = writer_agent(topic, material)
    print("【写作员】产出的周报：\n")
    print(report)


if __name__ == "__main__":
    orchestrator("我最近的学习和项目进展")
