"""
G2 · 确定性工作流：拉笔记 -> 摘要 -> 写回 Notion

运行：  python g2_workflow.py
该看到：固定跑完三步，最后打印「准备写回 Notion 的内容」并请你确认后再真正写入。

和 G1 的区别（重要认知）：
    G1 是让模型自己决定步骤（灵活但不可控）；
    G2 是我们把步骤写死成固定流程（可控、可复现）。
    真实系统里，能写死的流程就别交给模型「自由发挥」——这是 Workflow vs Agent 的核心取舍。

安全：写操作（写回 Notion）默认先预览、要你输入 y 确认才执行，避免 Agent 乱写。
"""

import json
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client
from mcp_helper import call_tool, find_tool_name, run

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
NOTES_FILE = DATA_DIR / "notes.json"


def step1_load_notes() -> list:
    if not NOTES_FILE.exists():
        print("没找到 notes.json，请先运行 c1_pull_notes.py")
        return []
    notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    print(f"[第1步] 载入 {len(notes)} 条笔记")
    return notes


def step2_summarize(notes: list) -> str:
    joined = "\n".join(f"《{n.get('title','')}》：{n.get('text','')}" for n in notes)
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": "把这些笔记汇总成一段简洁的『学习/工作小结』，200 字以内。"},
            {"role": "user", "content": joined},
        ],
        extra_body=NO_THINKING,
    )
    summary = resp.choices[0].message.content
    print("[第2步] 已生成摘要")
    return summary


def step3_write_back(summary: str) -> None:
    print("\n[第3步] 准备写回 Notion 的内容预览：\n")
    print("-" * 40)
    print(summary)
    print("-" * 40)

    confirm = input("\n确认写回 Notion 吗？(y/N) ").strip().lower()
    if confirm != "y":
        print("已取消写入（只是演示，没动你的 Notion）。")
        return

    # 找一个「创建页面 / 追加内容」类的工具，各版本命名不同
    tool_name = run(find_tool_name("create", "append", "post-page"))
    if not tool_name:
        print("没找到可写入的 Notion 工具，跳过实际写入。你可以先在 b3 里看看有哪些工具。")
        return

    print(f"使用工具 {tool_name} 写入……（若参数不匹配会报错，属正常，按你的 MCP 工具调整即可）")
    try:
        # 不同 MCP 参数差异较大，这里给一个常见形态，失败也不影响学习
        result = run(call_tool(tool_name, {"title": "每日小结", "content": summary}))
        print("写入结果：", result[:200])
    except Exception as e:  # noqa: BLE001
        print(f"写入调用报错（{e}）。这说明该工具参数和这里不一致，查看 b3 的工具说明再调整。")


def main() -> None:
    notes = step1_load_notes()
    if not notes:
        return
    summary = step2_summarize(notes)
    step3_write_back(summary)
    print("\n工作流结束。注意：整条流程的步骤是固定的，这就是『确定性 workflow』。")


if __name__ == "__main__":
    main()
