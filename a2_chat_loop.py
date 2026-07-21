"""
A2 · 能连续聊天的小程序

运行：  python a2_chat_loop.py
该看到：终端里出现「你：」提示，你输入一句，它回一句，可以一直聊。
        输入 quit 或 exit 退出。

关键点：模型本身没有记忆。它之所以「记得」上一句，是因为我们把
       完整的对话历史（messages 列表）每次都重新发给它。
       这就是最原始的「上下文」——后面的 Memory 关就是在优化它。
"""

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()

# 对话历史。每轮我们都往里面追加你的话和模型的话。
messages = [{"role": "system", "content": "你是一个简洁友好的中文助手。"}]

print("开始聊天吧（输入 quit 退出）\n")

while True:
    user_input = input("你：").strip()
    if user_input.lower() in {"quit", "exit"}:
        break
    if not user_input:
        continue

    messages.append({"role": "user", "content": user_input})

    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=messages,
        extra_body=NO_THINKING,
    )
    reply = resp.choices[0].message.content

    # 把模型的回复也存进历史，下一轮它才「记得」
    messages.append({"role": "assistant", "content": reply})
    print(f"AI：{reply}\n")
