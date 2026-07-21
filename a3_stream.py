"""
A3 · 流式输出：让回复一个字一个字蹦出来

运行：  python a3_stream.py
该看到：回复不是一次性出现，而是像打字一样逐字冒出来。

原理：加上 stream=True，服务器就不再等整段生成完，而是生成一点就发一点。
     这就是你现有网页里「AI 正在打字」效果的底层。
"""

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()

stream = client.chat.completions.create(
    model=QWEN_MODEL,
    messages=[
        {"role": "system", "content": "你是一个简洁的中文助手。"},
        {"role": "user", "content": "用三句话讲讲什么是大语言模型。"},
    ],
    extra_body=NO_THINKING,
    stream=True,
)

# 每一小块（chunk）里可能有一小段文字，我们拿到就立刻打印
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

print()  # 收尾换行
