"""
F1 · 用 SQLite 把对话存下来，重启还能读回历史

运行：  python f1_sqlite.py            正常聊天，可多次启动
        python f1_sqlite.py --new      开一个新会话
        python f1_sqlite.py --list     查看所有历史会话
该看到：聊完退出再启动，之前的对话还在（默认续上最近一个会话）。

为什么用数据库：前面几关的历史都只活在内存里，脚本一关就没。
    真实产品需要「持久化」——存进数据库。SQLite 是最轻量的选择，Python 自带、无需安装。
    这也是后面 Workflow、多会话管理的地基：先有稳定的「状态存储」。
"""

import sqlite3
import sys
import uuid
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client
from memory_store import build_memory_system_prompt

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = DATA_DIR / "chat.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    return conn


def list_conversations(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT conversation_id, COUNT(*), MAX(created_at) FROM messages GROUP BY conversation_id ORDER BY MAX(created_at) DESC"
    ).fetchall()
    if not rows:
        print("还没有任何会话。")
        return
    print("历史会话：")
    for cid, cnt, last in rows:
        print(f"  {cid}  ({cnt} 条消息，最后 {last})")


def latest_conversation(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT conversation_id FROM messages ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def load_messages(conn: sqlite3.Connection, cid: str) -> list:
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)
    ).fetchall()
    return [{"role": r, "content": c} for r, c in rows]


def save_message(conn: sqlite3.Connection, cid: str, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (cid, role, content),
    )
    conn.commit()


def main() -> None:
    conn = get_db()

    if "--list" in sys.argv:
        list_conversations(conn)
        return

    if "--new" in sys.argv:
        cid = str(uuid.uuid4())[:8]
        history = []
        print(f"开了新会话 {cid}\n")
    else:
        cid = latest_conversation(conn) or str(uuid.uuid4())[:8]
        history = load_messages(conn, cid)
        if history:
            print(f"续上会话 {cid}，已加载 {len(history)} 条历史：")
            # 给用户一个简洁的上下文预览
            for m in history[-4:]:
                # 截取开头部分，配合角色（role）信息，能让用户大致知道每条消息的主题或开头
                print(f"  {m['role']}: {m['content'][:40]}")
            print()
        else:
            print(f"新会话 {cid}\n")

    messages = [{"role": "system", "content": build_memory_system_prompt("你是一个简洁的中文助手。")}] + history

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        save_message(conn, cid, "user", user_input)

        resp = client.chat.completions.create(
            model=QWEN_MODEL, messages=messages, extra_body=NO_THINKING
        )
        reply = resp.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})
        save_message(conn, cid, "assistant", reply)
        print(f"AI：{reply}\n")

    print(f"对话已保存到数据库（会话 {cid}）。下次直接运行即可续上。")


if __name__ == "__main__":
    main()
