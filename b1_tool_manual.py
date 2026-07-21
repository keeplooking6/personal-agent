"""
B1 · 手动体会「工具」到底是什么

运行：  python b1_tool_manual.py
该看到：模型回答里包含了当前真实时间（模型自己是不知道时间的，是我们喂给它的）。

核心认知：模型不会自己联网、不会自己算数、也不知道现在几点。
        所谓「工具」，就是我们写的普通函数。模型能做的只有一件事：
        「告诉我们它想调用哪个函数、参数是什么」，
        真正去执行的是我们的代码，然后把结果再喂回给它。

这一关我们先「手动」走一遍这个流程，不让模型自动决定，方便你看清每一步。
"""

from datetime import datetime

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()


# 这就是一个「工具」——一个再普通不过的 Python 函数
def get_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 第一步：我们（假装是模型）决定要用这个工具，执行它拿到结果
tool_result = get_now()
print(f"[我们的代码执行了 get_now()，结果 = {tool_result}]\n")

# 第二步：把工具结果作为已知信息喂给模型，让它用自然语言回答
resp = client.chat.completions.create(
    model=QWEN_MODEL,
    messages=[
        {"role": "system", "content": "你是一个简洁的中文助手。"},
        {"role": "user", "content": "现在几点了？"},
        # 我们把工具结果塞进上下文，模型就「知道」时间了
        {"role": "user", "content": f"（系统提供的当前时间是：{tool_result}）"},
    ],
    extra_body=NO_THINKING,
)

print("AI：", resp.choices[0].message.content)
