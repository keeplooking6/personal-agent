"""
H2 · 评估：给你的 RAG 回答自动打分

运行：  python h2_eval.py
        python h2_eval.py --top-k 5
        python h2_eval.py --limit 3              # 只跑前 3 题（冒烟测试用）
        python h2_eval.py --report docs/reports/baseline.json
前提：  先跑过 d2_store_chroma.py。
该看到：对 eval_set.json 逐条打分，输出平均分和 baseline 报告。

阶段 5 增强：20 条 eval 集 + 可导出 JSON 报告。

本次修的三处：
  1) 取分不再取「第一个数字」。模型常写成「覆盖了3个要点中的2个，给5分」，
     旧写法会取到 3。现在要求裁判按「分数：X」格式输出，按格式解析，
     并在报告里标明每条分数是「按格式解析出来的」还是「兜底扫出来的」。
  2) 判分温度固定为 0。否则同一套题每次跑的分都不一样，没法当改动前后的基线。
  3) 补上检索层指标：期望命中的笔记有没有被检索到（覆盖率）。
     这样答错时能分清是「检索没找到资料」还是「找到了但答错」。
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client
from rag_core import rag_answer

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
EVAL_FILE = DATA_DIR / "eval_set.json"
REPORTS_DIR = Path(__file__).resolve().parent / "docs" / "reports"

# 裁判正常输出应该长这样：「分数：4」。按这个格式解析最可靠，
# 因为「第一个数字」和「最后一个数字」都可能被解释性文字带偏
# （「覆盖了3个要点中的2个，给5分」和「分数：5（备注：2处不准确）」各能坑掉一种）。
SCORE_PATTERN = re.compile(r"分数[：:]\s*([1-5])")


def load_eval_set() -> list[dict]:
    if EVAL_FILE.exists():
        return json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return []


def _parse_score(text: str) -> tuple[int, str]:
    """从裁判输出里取分数，返回 (分数, 取自哪种解析)。

    分三层，可靠性从高到低：
      format  —— 命中「分数：X」这种规定格式（正常情况）
      single  —— 整段回复就是一个数字
      scanned —— 兜底扫描，可能取错，报告里会标出来
    取不到返回 (0, "failed")。
    """
    raw = (text or "").strip()
    m = SCORE_PATTERN.search(raw)

    # 拿到分数就返回
    if m:
        return int(m.group(1)), "format"

    # 模型回复中没有别的内容，只有打分数字
    stripped = raw.strip("。.、 　\n")
    if len(stripped) == 1 and stripped in "12345":
        return int(stripped), "single"

    digits = re.findall(r"(?<![\d.])([1-5])(?![\d.])", raw)
    if digits:
        # 兜底取最后一个：模型的给分通常出现在解释之后（提示可能会取错，即取的并不是打分分数）
        return int(digits[-1]), "scanned"

    # 没有数字，说明评分失败（需人工查）
    return 0, "failed"


def _expected_titles(source_note: str) -> list[str]:
    """从 source_note 解析出期望命中的笔记标题。

    factual 写的是单个标题，summary 写「跨笔记：A / B」，rejection 写「无」。
    """
    raw = (source_note or "").strip()
    if not raw or raw == "无":
        return []
    raw = re.sub(r"^跨笔记[：:]\s*", "", raw)
    return [t.strip() for t in raw.split("/") if t.strip()]


def judge(question: str, expect: str, answer: str, category: str) -> tuple[int, str]:
    if category == "rejection":
        body = (
            f"问题：{question}\n"
            f"实际回答：{answer}\n\n"
            "这个问题应该无法从用户笔记中回答。若回答明确表示不知道/笔记里没有/无法回答，给 5 分；"
            "若编造了具体事实，给 1 分。"
        )
    else:
        body = (
            f"问题：{question}\n"
            f"参考要点：{expect}\n"
            f"实际回答：{answer}\n\n"
            "实际回答是否覆盖了参考要点？给 1-5 分（5=完全覆盖且正确，1=完全没答对）。"
        )
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "user",
             "content": body + "\n最后一行只输出：分数：X（X 是 1-5 的整数），不要输出别的数字。"},
        ],
        temperature=0,  # 固定裁判随机性，否则同一套题每次跑的分都不同，没法当基线
        extra_body=NO_THINKING,
    )
    return _parse_score(resp.choices[0].message.content)


def run_eval(top_k: int = 3, report_path: Path | None = None, limit: int = 0) -> dict:
    eval_set = load_eval_set()
    if not eval_set:
        print(f"未找到评估集 {EVAL_FILE}")
        return {}
    if limit > 0:
        eval_set = eval_set[:limit]
        print(f"[冒烟模式] 只跑前 {limit} 题\n")

    results = []
    scores = []
    by_category: dict[str, list[int]] = {}
    score_sources: dict[str, int] = {}
    coverage_values: list[float] = []
    retrieval_missed: list[str] = []

    for item in eval_set:
        rag = rag_answer(item["q"], k=top_k)
        score, source = judge(item["q"], item["expect"], rag["answer"], item.get("category", "factual"))
        scores.append(score)
        score_sources[source] = score_sources.get(source, 0) + 1

        cat = item.get("category", "factual")
        by_category.setdefault(cat, []).append(score)

        # 检索层：期望命中的笔记，实际检索到几篇
        expected = _expected_titles(item.get("source_note", ""))
        coverage = None
        if expected:
            found = [t for t in expected if t in rag["sources"]]
            coverage = len(found) / len(expected)
            coverage_values.append(coverage)
            if not found:
                retrieval_missed.append(item["q"])

        results.append(
            {
                "question": item["q"],
                "category": cat,
                "score": score,
                "score_source": source,
                "retrieval_coverage": None if coverage is None else round(coverage, 2), # 检索覆盖率
                "expected_notes": expected,
                "retrieved_notes": rag["sources"],
                "answer_preview": rag["answer"][:120],
            }
        )

        cov_text = "" if coverage is None else f" 检索覆盖 {coverage:.0%}"
        print(f"[{score}/5][{cat}]{cov_text} {item['q']}")
        print(f"      回答：{rag['answer'][:80]}\n")

    avg = sum(scores) / len(scores) if scores else 0
    cat_avg = {k: sum(v) / len(v) for k, v in by_category.items()}
    avg_cov = sum(coverage_values) / len(coverage_values) if coverage_values else 0

    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {"top_k": top_k, "limit": limit, "judge_temperature": 0},
        "total": len(scores),
        "average_score": round(avg, 2),
        "by_category": {k: round(v, 2) for k, v in cat_avg.items()},
        "retrieval": {
            "avg_coverage": round(avg_cov, 2),
            "missed_count": len(retrieval_missed),
            "missed_questions": retrieval_missed,
        },
        "score_source": score_sources,
        "results": results,
    }

    print(f"平均分：{avg:.2f} / 5  （共 {len(scores)} 条）")
    for cat, val in cat_avg.items():
        print(f"  [{cat}] 平均 {val:.2f}")
    if coverage_values:
        print(f"\n检索覆盖：{avg_cov:.0%}（期望命中的笔记里，实际检索到的比例）")
        if retrieval_missed:
            print(f"  有 {len(retrieval_missed)} 题一篇都没检索到：")
            for q in retrieval_missed:
                print(f"    - {q}")

    # 分数解析情况：scanned/failed 说明裁判没按格式输出，分数可能不准
    bad = score_sources.get("scanned", 0) + score_sources.get("failed", 0)
    if bad:
        print(f"\n⚠ 有 {bad} 条分数是兜底扫出来的（裁判没按「分数：X」输出），建议抽查：")
        for r in results:
            if r["score_source"] in ("scanned", "failed"):
                print(f"    - [{r['score_source']}] {r['question'][:40]}")

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告已保存：{report_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题，0 表示全跑")
    parser.add_argument("--report", type=str, default="")
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else REPORTS_DIR / "baseline.json"
    run_eval(top_k=args.top_k, report_path=report_path, limit=args.limit)


if __name__ == "__main__":
    main()
