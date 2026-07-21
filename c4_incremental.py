"""
C3 · 增量同步：按 last_edited_time 对比，
    只重新拉取变化过的页面，再对这些变化页重新切块并 upsert 到 Chroma。

运行：  python c4_incremental.py
前提：  先跑过 c1_pull_notes.py、c2_summarize.py、c3_chunk.py、d2_store_chroma.py。
该看到：打印出哪些页面有变动，重新拉取、切块并更新 Chroma。
"""

import asyncio
import json
import traceback
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from common import MCP_TOKEN, MCP_URL
from pipeline import split_text, CHROMA_DIR, COLLECTION, _build_chroma_metadata, summarize_note, get_embedding_function

DATA_DIR = Path(__file__).resolve().parent / "data"
NOTES_FILE = DATA_DIR / "notes.json"
SYNC_STATE_FILE = DATA_DIR / "sync_state.json"
CHUNKS_FILE = DATA_DIR / "chunks.json"
ENRICHED_FILE = DATA_DIR / "notes_enriched.json"

CHUNK_SIZE = 300
OVERLAP = 50


def _extract_text(call_result) -> str:
    parts = []
    for item in call_result.content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else ""


async def _mcp_call(name: str, args: dict, retries: int = 2) -> str:
    """调用 MCP 工具，失败时自动重试。"""
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    for attempt in range(retries + 1):
        try:
            async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments=args)
                    return _extract_text(result)
        except Exception as e:
            if attempt < retries:
                print(f"      [重试 {attempt + 1}/{retries}] {e}")
                await asyncio.sleep(1)
            else:
                raise
    return ""


def _find_titles(notes: list) -> str:
    """从已有笔记中提取前几个标题作为搜索关键词。"""
    titles = []
    for n in notes:
        t = n.get("title", "")
        if t:
            parts = t.split("：", 1)
            titles.append(parts[-1].strip() or parts[0].strip())
    seen = set()
    unique = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)
            if len(unique) >= 3:
                break
    return " ".join(unique)


async def incremental_sync() -> int:
    if not NOTES_FILE.exists():
        print(f"缺少 {NOTES_FILE}，请先运行 c1_pull_notes.py")
        return 0

    notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    sync_state = json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8-sig")) if SYNC_STATE_FILE.exists() else {}
    existing_chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8")) if CHUNKS_FILE.exists() else []

    if not notes:
        print("notes.json 为空，没有可同步的笔记")
        return 0

    # ── 1. 获取当前页面状态 ──
    query = _find_titles(notes)
    print(f"  搜索关键词: {query}")
    try:
        raw = await _mcp_call("API-post-search", {"query": query, "page_size": 50})
    except Exception:
        print("  [搜索] MCP 不可用，逐个检查页面 timestamps")
        raw = ""

    current = {}
    if raw:
        try:
            data = json.loads(raw)
            results = data if isinstance(data, list) else data.get("results", [])
            for r in results if isinstance(results, list) else []:
                pid = r.get("id", "")
                let = r.get("last_edited_time", "")
                if pid and let:
                    current[pid] = let
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    # 批量搜索没覆盖到的页面，逐个查询
    for note in notes:
        print("如果标题查不到该页面，就用pageid查")
        pid = note.get("id", "")
        if pid and pid not in current:
            try:
                text = await _mcp_call("API-retrieve-a-page", {"page_id": pid})
                data = json.loads(text)
                let = data.get("last_edited_time") if isinstance(data, dict) else None
                if let:
                    current[pid] = let
            except Exception:
                pass

    # ── 2. 找出有变化的页面 ──
    changed_ids = []
    for note in notes:
        pid = note["id"]
        new_time = current.get(pid, "")
        synced_time = sync_state.get(pid, "")
        if new_time and new_time != synced_time:
            changed_ids.append(pid)
            print(f"  [变化] {note.get('title', pid)}: {synced_time or '首次'} → {new_time}")

    if not changed_ids:
        print("  没有页面发生变化")
        return 0

    print(f"  共 {len(changed_ids)} 个页面发生变化")

    # ── 3. 重新拉取变化页的完整内容并更新 Chroma ──
    import chromadb

    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        collection = chroma_client.get_collection(COLLECTION, embedding_function=get_embedding_function())
    except Exception:
        print(f"  Chroma 集合 '{COLLECTION}' 不存在，请先运行 d2_store_chroma.py")
        return 0

    for note in notes:
        if note["id"] not in changed_ids:
            continue

        pid = note["id"]
        title = note.get("title", pid)
        print(f"  [拉取] {title} ...")

        try:
            text = await _mcp_call("API-retrieve-page-markdown", {"page_id": pid})
            if text:
                try:
                    data = json.loads(text)
                    note["text"] = data.get("markdown", text)[:20000]
                except json.JSONDecodeError:
                    note["text"] = text[:20000]
            else:
                text = await _mcp_call("API-get-block-children", {"block_id": pid})
                note["text"] = text[:20000]
        except Exception as e:
            print(f"    ⚠ 拉取失败: {e}")
            continue

        note["last_edited_time"] = current.get(pid, note.get("last_edited_time", ""))

        # ── 4. 对更新内容重新打标 ──
        print(f"  [分类] {title} ...")
        enrichment = summarize_note(note)
        note["note_type"] = enrichment["note_type"]
        note["insight_type"] = enrichment["insight_type"]
        note["summary"] = enrichment["summary"]
        note["tags"] = enrichment["tags"]

        # ── 5. 重新切块（此时 note 已有新鲜 enrichment 字段） ──
        new_chunks = []
        for i, piece in enumerate(split_text(note["text"], CHUNK_SIZE, OVERLAP)):
            new_chunks.append({
                "chunk_id": f"{pid}#{i}",
                "note_id": pid,
                "title": note.get("title", ""),
                "text": piece,
                "note_type": note["note_type"],
                "insight_type": note["insight_type"] or "",
                "summary": note["summary"],
                "tags": note["tags"],
            })

        # ── 6. 从 Chroma 删除旧块，添加新块 ──
        old = collection.get(where={"note_id": pid})
        old_ids = old.get("ids", [])
        if old_ids:
            collection.delete(ids=old_ids)
        if new_chunks:
            collection.add(
                ids=[c["chunk_id"] for c in new_chunks],
                documents=[c["text"] for c in new_chunks],
                metadatas=[_build_chroma_metadata(c) for c in new_chunks],
            )

        existing_chunks = [c for c in existing_chunks if c.get("note_id") != pid] + new_chunks
        print(f"    [OK] 已更新 {len(new_chunks)} 个块")

    # ── 7. 保存更新后的文件 ──
    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    CHUNKS_FILE.write_text(json.dumps(existing_chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    for pid in changed_ids:
        sync_state[pid] = current.get(pid, "")
    SYNC_STATE_FILE.write_text(json.dumps(sync_state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 8. 同步更新 enriched 文件（note 此时已有新鲜 enrichment 字段） ──
    if ENRICHED_FILE.exists():
        enriched = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))
        changed_map = {n["id"]: n for n in notes if n["id"] in changed_ids}
        for i, e in enumerate(enriched):
            if e["id"] in changed_map:
                enriched[i] = changed_map[e["id"]]
        ENRICHED_FILE.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    elif changed_ids:
        changed_notes = [n for n in notes if n["id"] in changed_ids]
        ENRICHED_FILE.write_text(json.dumps(changed_notes, ensure_ascii=False, indent=2), encoding="utf-8")

    return len(changed_ids)


def main() -> None:
    try:
        count = asyncio.run(incremental_sync())
    except BaseException as e:
        print(f"增量同步失败：{e}")
        traceback.print_exc()
        count = 0

    if count > 0:
        print(f"增量同步完成，更新了 {count} 个页面")
    else:
        print("没有需要更新的页面")


if __name__ == "__main__":
    main()
