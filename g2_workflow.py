"""
G2 · 确定性工作流：拉笔记 -> 摘要 -> 写回 Notion

运行：  python g2_workflow.py
该看到：固定跑完三步；第 3 步确认后，模型按工具契约生成调用与参数，
        在你的 Notion 里真实新建一页子页面「每日小结 <日期>」，并打印创建结果。

和 G1 的区别（重要认知）：
    G1 是让模型自己决定步骤（灵活但不可控）；
    G2 是我们把步骤写死成固定流程（可控、可复现）。
    真实系统里，能写死的流程就别交给模型「自由发挥」——这是 Workflow vs Agent 的核心取舍。

第 3 步的设计（模式 3：流程写死，参数交给模型）——分三层看「谁决定什么」：
    1. 工具能力面：代码收窄。只把 search + create 两个工具声明给模型（WRITE_TOOLS），
       服务器上其余工具不暴露——授权面就是能力面（见 思考.md）。
    2. 流程与顺序：prompt 固化。system prompt 点名这两个工具、点名「先搜索、后创建」，
       但这是自然语言软约束，不是代码闸门：代码里没有硬编码任何一次工具调用。
    3. 调用与参数：模型生成。发哪次调用、参数填什么由模型输出决定，代码只做通用分发
       （call_tool(名字, 参数)）与结果回填；唯一的工具专属逻辑是 post-page 的本地校验
       和成功判定。这里模型无法凭空生成父页面 id 只存在于搜索结果里，摘要怎么拆成
       段落块也得现场生成，开发期写不出来。
    两道防呆：
      A. schema 里写明结构约束（rich_text 元素必须是对象等），引导模型一次生成对；
      B. 调 MCP 前先本地校验/修复参数：能修的就地修（删畸形元素、补标准结构），
         修不了的把明确错误回填给模型让它重试，而不是把坏参数直接发给 Notion 报 400。

安全：写操作（写回 Notion）默认先预览、要你输入 y 确认才执行，避免 Agent 乱写。
      写回只「新增」一个子页面，不修改、不删除任何已有页面。
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client
from mcp_helper import call_tool, list_tools, run

client = get_client()

DATA_DIR = Path(__file__).resolve().parent / "data"
NOTES_FILE = DATA_DIR / "notes.json"

# 第 3 步最多让模型来回调几轮工具，防止死循环
MAX_WRITE_STEPS = 5

# 精简后的工具声明（字段名/必填项与 MCP 服务器 inputSchema 一致）。
# 服务端上下文 8192，可以带 items 级结构约束（方案 A），
# 但整份原始 schema 仍太大，这里压缩说明文字、保留结构。
WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "API-post-search",
            "description": "按标题关键词搜索 Notion，返回页面/数据库列表（每项含 id、title、type）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如笔记标题里的词"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "API-post-page",
            "description": "在 Notion 新建一个子页面。必须先搜索到真实的父页面，用它的 id。",
            "parameters": {
                "type": "object",
                "required": ["parent", "properties"],
                "properties": {
                    "parent": {
                        "type": "object",
                        "required": ["type", "page_id"],
                        "description": "父页面对象，id 必须来自搜索结果，"
                                       '形如 {"type": "page_id", "page_id": "<uuid>"}',
                        "properties": {
                            "type": {"type": "string", "const": "page_id"},
                            "page_id": {"type": "string", "description": "来自搜索结果的真实页面 id"},
                        },
                    },
                    "properties": {
                        "type": "object",
                        "description": "页面标题属性，子页面标题键是 title。",
                        "properties": {
                            "title": {
                                "type": "object",
                                "required": ["title"],
                                "properties": {
                                    "title": {
                                        "type": "array",
                                        "description": "标题文字数组，一个元素即可",
                                        "items": {
                                            "type": "object",
                                            "required": ["type", "text"],
                                            "properties": {
                                                "type": {"type": "string", "const": "text"},
                                                "text": {"type": "object",
                                                         "required": ["content"],
                                                         "properties": {"content": {"type": "string"}}},
                                            },
                                        },
                                    }
                                },
                            }
                        },
                    },
                    "children": {
                        "type": "array",
                        "description": "正文块数组，摘要拆成 1~3 个 paragraph 块",
                        "items": {
                            "type": "object",
                            "required": ["object", "type", "paragraph"],
                            "properties": {
                                "object": {"type": "string", "const": "block"},
                                "type": {"type": "string", "const": "paragraph"},
                                "paragraph": {
                                    "type": "object",
                                    "required": ["rich_text"],
                                    "properties": {
                                        "rich_text": {
                                            "type": "array",
                                            "description": "每个元素必须是对象 "
                                                           '{"type": "text", "text": {"content": "段落文字"}}；'
                                                           "禁止 plain_text / annotations 等响应字段，"
                                                           "也不要往数组里放裸字符串",
                                            "items": {
                                                "type": "object",
                                                "required": ["type", "text"],
                                                "properties": {
                                                    "type": {"type": "string", "const": "text"},
                                                    "text": {"type": "object",
                                                             "required": ["content"],
                                                             "properties": {"content": {"type": "string"}}},
                                                },
                                            },
                                        }
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
]


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


def _try_parse_page_created(text: str) -> str | None:
    """API-post-page 成功后 Notion 返回页面对象（含 id/url），试着抠出来。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("id") and not data.get("code"):
        return f"id={data['id']} url={data.get('url', '')}"
    return None


def _repair_page_args(args: dict) -> tuple[dict, str | None]:
    """方案 B：调 MCP 前先做本地契约校验/修复。

    模型生成深层嵌套 JSON 容易出畸形（如 rich_text 里混入裸字符串 "plain_text"）。
    这里「能修的就地修」：删畸形元素、补标准结构、规范化必填字段；
    修不了的返回明确错误，让模型对着错误重试，
    而不是把坏参数直接发给 Notion 吃 400。
    返回 (修复后的参数, 错误说明或 None)。
    """
    errors: list[str] = []

    # 1) parent：必须给出真实页面 id，并规范成 page_id 形态
    parent = args.get("parent")
    norm_parent = None
    if isinstance(parent, dict):
        if parent.get("page_id"):
            norm_parent = {"type": "page_id", "page_id": parent["page_id"]}
        elif parent.get("database_id"):
            norm_parent = {"type": "database_id", "database_id": parent["database_id"]}
    if norm_parent is None:
        errors.append('parent 必须是对象且带 page_id，如 {"type": "page_id", "page_id": "<uuid>"}')

    # 2) properties：抽出标题文字并规范成标准结构
    content_str = None
    props = args.get("properties")
    if isinstance(props, dict):
        tt = props.get("title")
        if isinstance(tt, dict):
            rt = tt.get("title")
            if isinstance(rt, list) and rt and isinstance(rt[0], dict):
                txt = rt[0].get("text")
                if isinstance(txt, dict):
                    content_str = txt.get("content")
    if not content_str:
        errors.append("properties.title.title[0].text.content 缺失，找不到标题文字")

    # 3) children：paragraph 块逐个清洗 rich_text
    children = args.get("children")
    cleaned: list = []
    had_children = children is not None
    if had_children:
        if not isinstance(children, list):
            children = [children]
        for blk in children:
            if not isinstance(blk, dict):
                continue  # 裸元素直接丢弃
            para = blk.get("paragraph")
            # 容忍模型把 rich_text 放错层级：block 直接带 rich_text
            if not isinstance(para, dict) and isinstance(blk.get("rich_text"), list):
                para = {"rich_text": blk["rich_text"]}
            if not isinstance(para, dict) or not isinstance(para.get("rich_text"), list):
                continue
            clean_rt: list = []
            for item in para["rich_text"]:
                if not isinstance(item, dict):
                    continue  # 裸字符串（如 "plain_text"）→ 丢弃
                txt = item.get("text")
                if not isinstance(txt, dict) or not isinstance(txt.get("content"), str):
                    continue
                clean_rt.append({"type": "text", "text": {"content": txt["content"]}})
            if clean_rt:
                cleaned.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": clean_rt},
                })
        if had_children and not cleaned:
            errors.append("children 里的 paragraph 块都没有有效文字")

    if errors:
        return args, "；".join(errors)

    out: dict = {"parent": norm_parent,
                 "properties": {"title": {"title": [
                     {"type": "text", "text": {"content": content_str}}]}}}
    if had_children:
        out["children"] = cleaned
    return out, None


async def _write_back_async(summary: str, note_titles: list) -> str:
    """第 3 步的核心：工具面由代码收窄、顺序由 prompt 固化，
    调用与参数由模型生成；代码只做通用分发、参数校验和错误回填。"""
    all_tools = await list_tools()
    have = {t.name for t in all_tools}
    # 检验代码层面选用的工具，在notion mcp server服务器中是否有提供
    missing = [wt["function"]["name"] for wt in WRITE_TOOLS if wt["function"]["name"] not in have]
    if missing:
        return f"MCP 服务器上找不到工具 {missing}，跳过写入。可先运行 b3 查看有哪些工具。"

    titles_hint = "；".join(note_titles) or "（无）"
    messages = [
        {"role": "system", "content": (
            "你要把一段摘要作为新页面写进用户的 Notion。规则：\n"
            "1. 先用 API-post-search 搜索一个真实存在的页面作为父页面"
            "（可从用户笔记标题里选词搜索，搜不到就换个词再试一次）；\n"
            "2. 再用 API-post-page 在该页面下新建子页面，标题形如「每日小结 2026-09-07」"
            "（用今天日期），正文 children 拆成 1~3 个 paragraph 块写入摘要；\n"
            "3. 严格按工具 schema 生成参数：rich_text 的每个元素必须是对象"
            '{"type": "text", "text": {"content": "文字"}}，不要写 plain_text / '
            "annotations 等响应字段，也不要把字符串直接放进 rich_text 数组；\n"
            "4. 父页面 id 必须来自搜索结果，不要凭空编造；只选 page 类型，不要用数据库；\n"
            "5. 只新增页面，不要调用任何修改/删除类工具。"
        )},
        {"role": "user", "content": (
            f"用户现有笔记标题（搜索线索）：{titles_hint}\n\n"
            f"要写回的摘要：\n{summary}"
        )},
    ]

    for step in range(1, MAX_WRITE_STEPS + 1):
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=QWEN_MODEL, messages=messages, tools=WRITE_TOOLS,
            extra_body=NO_THINKING,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "（模型未生成任何调用，已结束）"
        messages.append(msg)
        for call in msg.tool_calls:
            print(f"\n  [写回·第{step}轮] 模型调用 {call.function.name}")
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                text = "(参数不是合法 JSON，未调用工具。请重新生成严格 JSON 参数)"
                print(f"    ⚠ {text}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": text})
                continue
            if call.function.name == "API-post-page":
                # 方案 B：先本地校验/修复，坏参数不发到 Notion
                repaired, fix_err = _repair_page_args(args)
                if fix_err:
                    text = f"(本地校验失败，未调用 Notion：{fix_err}。请修正参数后重试)"
                    print(f"    ⚠ {text}")
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": text[:1500]})
                    continue
                if json.dumps(repaired, ensure_ascii=False) != json.dumps(args, ensure_ascii=False):
                    print(f"    ↻ 参数不标准，已本地修复："
                          f"{json.dumps(repaired, ensure_ascii=False)[:300]}")
                args = repaired
            print(f"    参数：{json.dumps(args, ensure_ascii=False)[:300]}")
            try:
                text = await call_tool(call.function.name, args)
            except Exception as e:  # noqa: BLE001
                text = f"(调用失败: {e})"
            print(f"    结果：{text[:300]}")
            # 结果回填给模型：报错（如参数不对/父页面不存在）模型能据此修正重试
            messages.append({"role": "tool", "tool_call_id": call.id, "content": text[:1500]})
            # 页面创建成功即达成目标
            if call.function.name == "API-post-page":
                created = _try_parse_page_created(text)
                if created:
                    return f"✅ 已创建新页面：{created}"
    return f"达到 {MAX_WRITE_STEPS} 轮上限仍未成功，写入中止。"


def step3_write_back(summary: str, note_titles: list) -> None:
    print("\n[第3步] 准备写回 Notion 的内容预览：\n")
    print("-" * 40)
    print(summary)
    print("-" * 40)

    confirm = input("\n确认写回 Notion 吗？(y/N) ").strip().lower()
    if confirm != "y":
        print("已取消写入（只是演示，没动你的 Notion）。")
        return

    print("\n本次写回：顺序由 prompt 固化（搜索父页面 -> 创建子页面）、"
          "工具面被代码收窄到 2 个，但生成调用和参数的是模型，代码只负责校验和分发")
    print(f"（父页面：从你的 {len(note_titles)} 篇笔记中搜索；"
          f"新页面：子页面「每日小结 {date.today():%Y-%m-%d}」）\n")
    result = run(_write_back_async(summary, note_titles))
    print("\n写入结果：", result[:600])


def main() -> None:
    notes = step1_load_notes()
    if not notes:
        return
    summary = step2_summarize(notes)
    step3_write_back(summary, [n.get("title", "") for n in notes])
    print("\n工作流结束。注意：整条流程的步骤是固定的，这就是『确定性 workflow』；"
          "但第 3 步的调用与参数由模型按工具契约生成（工具面由代码收窄、顺序由 prompt 固化），"
          "这是『Workflow 里嵌 LLM 节点』的常见组合。")


if __name__ == "__main__":
    main()
