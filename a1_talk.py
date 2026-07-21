"""
A1 · 第一次和你的模型说上话

运行：  python a1_talk.py
该看到：终端打印出 Qwen 的一句回复。

这就是所有 Agent 的最底层：一次「请求 -> 回复」。
后面所有花哨的东西（工具、记忆、RAG）都只是在这一步外面套壳。
"""

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()

# messages 是一个列表，每条是一个「谁说的 + 说了什么」。
# role 常见三种：system（给模型定规矩）、user（你）、assistant（模型）。
resp = client.chat.completions.create(
    model=QWEN_MODEL,
    messages=[
        {"role": "system", "content": "你是一个简洁的中文助手。"},
        {"role": "user", "content": "用一句话介绍你自己。"},
    ],
    extra_body=NO_THINKING,
)

# 模型的回复藏在 choices[0].message.content 里
print(resp.choices[0].message.content)
