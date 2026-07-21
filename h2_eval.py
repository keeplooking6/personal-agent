"""
H2 · 评估：给你的 RAG 回答自动打分

运行：  python h2_eval.py
        python h2_eval.py --top-k 5
        python h2_eval.py --report docs/reports/baseline.json
前提：  先跑过 d2_store_chroma.py。
该看到：对 eval_set.json 逐条打分，输出平均分和 baseline 报告。

阶段 5 增强：20 条 eval 集 + 可导出 JSON 报告。
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client
from rag_core import rag_answer

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
EVAL_FILE = DATA_DIR / "eval_set.json"
REPORTS_DIR = Path(__file__).resolve().parent / "docs" / "reports"


def load_eval_set() -> list[dict]:
    if EVAL_FILE.exists():
        return json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return []


def judge(question: str, expect: str, answer: str, category: str) -> int:
    if category == "rejection":
        prompt = (
            f"问题：{question}\n"
            f"实际回答：{answer}\n\n"
            "这个问题应该无法从用户笔记中回答。若回答明确表示不知道/笔记里没有/无法回答，给 5 分；"
            "若编造了具体事实，给 1 分。只输出一个 1-5 的数字。"
        )
    else:
        prompt = (
            f"问题：{question}\n"
            f"参考要点：{expect}\n"
            f"实际回答：{answer}\n\n"
            "实际回答是否覆盖了参考要点？给 1-5 分（5=完全覆盖且正确，1=完全没答对）。"
            "只输出一个数字。"
        )
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        extra_body=NO_THINKING,
    )
    text = resp.choices[0].message.content.strip()
    for ch in text:
        if ch.isdigit():
            return int(ch)
    return 0


def run_eval(top_k: int = 3, report_path: Path | None = None) -> dict:
    eval_set = load_eval_set()
    if not eval_set:
        print(f"未找到评估集 {EVAL_FILE}")
        return {}

    results = []
    scores = []
    by_category: dict[str, list[int]] = {}

    for item in eval_set:
        rag = rag_answer(item["q"], k=top_k)
        score = judge(item["q"], item["expect"], rag["answer"], item.get("category", "factual"))
        scores.append(score)
        cat = item.get("category", "factual")
        by_category.setdefault(cat, []).append(score)
        results.append(
            {
                "question": item["q"],
                "category": cat,
                "score": score,
                "answer_preview": rag["answer"][:120],
                "sources": rag["sources"],
            }
        )
        print(f"[{score}/5][{cat}] {item['q']}")
        print(f"      回答：{rag['answer'][:80]}\n")

    avg = sum(scores) / len(scores) if scores else 0
    cat_avg = {k: sum(v) / len(v) for k, v in by_category.items()}

    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {"top_k": top_k},
        "total": len(scores),
        "average_score": round(avg, 2),
        "by_category": {k: round(v, 2) for k, v in cat_avg.items()},
        "results": results,
    }

    print(f"平均分：{avg:.2f} / 5  （共 {len(scores)} 条）")
    for cat, val in cat_avg.items():
        print(f"  [{cat}] 平均 {val:.2f}")

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告已保存：{report_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--report", type=str, default="")
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else REPORTS_DIR / "baseline.json"
    run_eval(top_k=args.top_k, report_path=report_path)


if __name__ == "__main__":
    main()
