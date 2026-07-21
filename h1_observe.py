"""
H1 · 可观测性：给每次调用加上日志、耗时、token 统计

运行：  python h1_observe.py
该看到：每次模型调用后，打印出耗时（秒）和用了多少 token（输入/输出/合计）。

observe.py 把同样能力封装成 TraceLogger，供 b4/d4/agent_core 复用。
"""

from common import QWEN_MODEL, NO_THINKING, get_client
from observe import TraceLogger, timed_call

client = get_client()


def observed_chat(prompt: str, trace: TraceLogger) -> str:
    resp, elapsed = timed_call(
        client.chat.completions.create,
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        extra_body=NO_THINKING,
    )
    trace.log_llm("h1_demo", resp, elapsed, prompt=prompt[:40])
    return resp.choices[0].message.content


def main() -> None:
    trace = TraceLogger("h1-demo")
    for q in ["用一句话解释 RAG", "用一句话解释 Agent 的记忆", "用一句话解释 workflow 和 agent 的区别"]:
        print(f"\n问：{q}")
        answer = observed_chat(q, trace)
        print("答：", answer)
    trace.print_summary()


if __name__ == "__main__":
    main()
