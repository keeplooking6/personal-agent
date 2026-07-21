"""
D4 · 完整 RAG：检索你的笔记 + 让模型据此回答（带出处）

运行：  python d4_rag_answer.py "我在学什么"
        python d4_rag_answer.py "我在学什么" --top-k 5
前提：  先跑过 d2_store_chroma.py。
该看到：模型基于你真实笔记内容作答，并标注答案来自哪几条笔记。

阶段 5 增强：集成 rag_core + observe.TraceLogger。
"""

import sys

from observe import TraceLogger
from rag_core import rag_answer


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "我最近在学什么、有哪些项目？"
    top_k = 3
    if "--top-k" in sys.argv:
        idx = sys.argv.index("--top-k")
        if idx + 1 < len(sys.argv):
            top_k = int(sys.argv[idx + 1])

    trace = TraceLogger()
    result = rag_answer(question, k=top_k, trace=trace)

    print(f"问题：{question}\n")
    print("AI：", result["answer"])
    print(f"\n来源：{', '.join(result['sources'])}")
    trace.print_summary()


if __name__ == "__main__":
    main()
