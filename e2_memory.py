"""
E2 · 长期记忆：记住「关于你这个人」的事实，跨会话还在

运行：  python e2_memory.py
        第一次跑：和它聊几句（比如告诉它你在学什么、有什么项目），输入 quit 退出。
        第二次跑：它开场就会「记得」你上次说过的事。
该看到：退出时它从对话里抽取关于你的事实，存进 data/memory.json；
        下次启动时自动读回来，开场白里体现出来。

RAG vs Memory 的区别（重点）：
    RAG 检索的是「外部知识/笔记内容」；
    Memory 记的是「关于用户本人和交互」的事实（偏好、正在做的事、身份）。
    两者都靠「写入 + 检索」，但服务的对象不同。
"""

import json
from pathlib import Path

from memory_store import build_memory_system_prompt, extract_facts, load_memory, save_memory
from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def main() -> None:
    facts = load_memory()

    memory_note = build_memory_system_prompt("你是用户的私人助手。")
    messages = [{"role": "system", "content": memory_note}]

    if facts:
        print("（已加载长期记忆）我记得：", "；".join(facts), "\n")
    else:
        print("（还没有关于你的记忆，这次聊完我会记住）\n")

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        resp = client.chat.completions.create(
            model=QWEN_MODEL, messages=messages, extra_body=NO_THINKING
        )
        reply = resp.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})
        print(f"AI：{reply}\n")

    # 退出时更新长期记忆
    new_facts = extract_facts(messages, facts)
    save_memory(new_facts)
    print("\n已更新长期记忆：", "；".join(new_facts))
    print(f"（存到 data/memory.json，下次启动会自动读回）")


if __name__ == "__main__":
    main()
