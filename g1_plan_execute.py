"""
G1 · 先规划再执行（Plan-and-Execute 最小版）

运行：  python g1_plan_execute.py "帮我准备一次 Agent 学习分享"
        （不带参数用默认任务）
该看到：模型先输出一份「步骤计划」，然后逐条执行，最后汇总成结果。

和之前的区别：前面模型都是「一步到位」直接回答。复杂任务这样容易乱。
    Plan-and-Execute 的思路是：先想清楚步骤（规划），再一步步做（执行）。
    这是 Agent「会规划」的最小体现，也是 Workflow 的雏形。
"""

import json
import sys

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()


def make_plan(task: str) -> list[str]:
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": "把用户任务拆成 3-5 个有序步骤。只输出 JSON 数组，元素是简短中文步骤。"},
            {"role": "user", "content": task},
        ],
        extra_body=NO_THINKING,
    )
    raw = resp.choices[0].message.content
    start, end = raw.find("["), raw.rfind("]")
    try:
        return json.loads(raw[start : end + 1])
    except Exception:  # noqa: BLE001
        return [raw]


def do_step(task: str, step: str, done: list[str]) -> str:
    context = "\n".join(f"- {s}" for s in done) or "（还没有）"
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": "你在按计划一步步完成任务。只完成当前这一步，简洁输出结果。"},
            {"role": "user", "content": f"总任务：{task}\n已完成：\n{context}\n\n现在执行这一步：{step}"},
        ],
        extra_body=NO_THINKING,
    )
    return resp.choices[0].message.content


def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else "帮我准备一次关于 AI Agent 的 10 分钟学习分享"

    print(f"任务：{task}\n")
    plan = make_plan(task)
    print("规划出的步骤：")
    for i, s in enumerate(plan, 1):
        print(f"  {i}. {s}")
    print()

    done_results = []
    for i, step in enumerate(plan, 1):
        print(f"--- 执行第 {i} 步：{step} ---")
        result = do_step(task, step, done_results)
        print(result, "\n")
        done_results.append(f"{step} -> {result}")

    print("=== 全部步骤执行完毕 ===")


if __name__ == "__main__":
    main()
