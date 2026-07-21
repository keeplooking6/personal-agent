"""
长期记忆存储：从 e2_memory.py 抽出的可复用模块。

Memory 分层（面试用）：
  - Working Memory: 当前 messages 窗口
  - Session Memory: SQLite 历史（f1）
  - Compressed Memory: e1 摘要
  - Long-term Memory: 本模块的 memory.json 用户事实
"""

from __future__ import annotations

import json
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
MEMORY_FILE = DATA_DIR / "memory.json"


def load_memory() -> list[str]:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return []


def save_memory(facts: list[str]) -> None:
    MEMORY_FILE.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")


def build_memory_system_prompt(base: str = "你是用户的私人助手。") -> str:
    facts = load_memory()
    if facts:
        return base + "你已知的关于用户的信息：" + "；".join(facts)
    return base + "你还不了解这个用户。"


def extract_facts(conversation: list, old_facts: list[str] | None = None) -> list[str]:
    old_facts = old_facts or []
    client = get_client()
    text = "\n".join(f"{m['role']}: {m['content']}" for m in conversation if m["role"] != "system")
    prompt = (
        "从下面对话中，抽取关于『用户本人』值得长期记住的事实"
        "（如姓名、偏好、正在学的东西、项目）。\n"
        f"已知旧事实：{old_facts}\n"
        "对话：\n" + text + "\n\n"
        "只输出一个 JSON 数组，元素是简短中文句子，合并旧事实并去重。"
    )
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        extra_body=NO_THINKING,
    )
    raw = resp.choices[0].message.content.strip()
    try:
        start, end = raw.find("["), raw.rfind("]")
        return json.loads(raw[start : end + 1])
    except Exception:  # noqa: BLE001
        return old_facts
