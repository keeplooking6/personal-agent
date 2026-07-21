"""
RAG 参数实验：对比 chunk_size 和 top_k 对 eval 分数的影响。

运行：  python run_experiments.py
该看到：多组配置的 eval 平均分对比，报告保存到 docs/reports/rag_experiments.json

前提：data/notes.json 已存在（可用 c1 或示例数据）。
"""

import json
from datetime import datetime
from pathlib import Path

from h2_eval import run_eval
from pipeline import build_chunks, store_chroma

REPORTS_DIR = Path(__file__).resolve().parent / "docs" / "reports"


def run_one(chunk_size: int, overlap: int, top_k: int) -> dict:
    chunks = build_chunks(chunk_size=chunk_size, overlap=overlap)
    store_chroma(chunks)
    print(f"\n=== chunk_size={chunk_size} overlap={overlap} top_k={top_k} chunks={len(chunks)} ===")
    report = run_eval(top_k=top_k, report_path=None)
    return {
        "chunk_size": chunk_size,
        "overlap": overlap,
        "top_k": top_k,
        "chunk_count": len(chunks),
        "average_score": report.get("average_score", 0),
        "by_category": report.get("by_category", {}),
    }


def main() -> None:
    experiments = [
        {"chunk_size": 300, "overlap": 50, "top_k": 3},
        {"chunk_size": 600, "overlap": 80, "top_k": 3},
        {"chunk_size": 300, "overlap": 50, "top_k": 5},
    ]

    results = []
    for exp in experiments:
        results.append(run_one(**exp))

    summary = {
        "timestamp": datetime.now().isoformat(),
        "experiments": results,
        "conclusion_hint": "对比 average_score，选最高分的 chunk_size/top_k 组合作为默认配置",
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "rag_experiments.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 实验汇总 ===")
    for r in results:
        print(
            f"chunk={r['chunk_size']} top_k={r['top_k']} "
            f"chunks={r['chunk_count']} avg={r['average_score']}"
        )
    print(f"\n完整报告：{out}")


if __name__ == "__main__":
    main()
