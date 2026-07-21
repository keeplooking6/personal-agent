"""
E1 · 短期记忆：把长对话压缩成一小段摘要

运行：  python e1_summary.py
该看到：先造一段很长的假对话，再让模型把它压成几句话的摘要。

为什么需要：A2 里我们把「完整历史」每轮都发给模型。对话一长，token 就爆了、又慢又贵。
    办法：把早期对话压成一段摘要，只保留最近几轮原文。这就是「上下文压缩」，
    是控制上下文预算最常用的一招，也是「记忆」和「省钱」的交汇点。
"""

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()

# 造一段较长的历史对话
long_history = [
    {"role": "user", "content": "我叫小李，在学做 AI Agent。"},
    {"role": "assistant", "content": "你好小李，很高兴帮你学习 Agent。"},
    {"role": "user", "content": "我有个项目叫 notion-mcp-chat，用 Next.js 和本地 Qwen。"},
    {"role": "assistant", "content": "了解，这是个把 Notion 和本地模型连起来的项目。"},
    {"role": "user", "content": "我这周想先搞懂 RAG，然后做记忆。"},
    {"role": "assistant", "content": "计划清晰，先 RAG 再 Memory 是合理顺序。"},
    {"role": "user", "content": "对了我比较喜欢简洁、少废话的回答。"},
    {"role": "assistant", "content": "好的，我会尽量简洁。"},
]


def summarize(history: list) -> str:
    text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": "把下面的对话压缩成不超过 3 句话的摘要，保留关键事实。"},
            {"role": "user", "content": text},
        ],
        extra_body=NO_THINKING,
    )
    return resp.choices[0].message.content


summary = summarize(long_history)
print("原始对话轮数：", len(long_history))
print("\n压缩后的摘要：\n", summary)
print("\n实际使用时：把这段摘要作为一条 system 消息放最前面，就能『记住』早期内容而不必带全部原文。")
