"""
数据管道：chunk + 入库 + enrichment，供 c2/c3/c4/d2 复用。

P1 增强：优先读取 notes_enriched.json（c2_summarize.py 产物），
让每个 chunk 的 metadata 携带 note_type / insight_type / summary / tags，
检索时可按类型过滤。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from common import QWEN_MODEL, NO_THINKING, get_client

DATA_DIR = Path(__file__).resolve().parent / "data"
NOTES_FILE = DATA_DIR / "notes.json"
ENRICHED_FILE = DATA_DIR / "notes_enriched.json"  # c2_summarize.py 产物
CHUNKS_FILE = DATA_DIR / "chunks.json"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION = "notes"

# ── Embedding: 支持中文的向量模型 ──

_ef = None

def get_embedding_function():
    """获取 embedding 函数，延迟初始化，首次自动下载模型。"""
    global _ef
    if _ef is None:
        from bge_onnx_embedding import BGEOnnxEmbeddingFunction
        _ef = BGEOnnxEmbeddingFunction()
    return _ef

# ── Enrichment: 笔记分类标签 ──

VALID_NOTE_TYPES = {"knowledge", "growth"}
VALID_INSIGHT_TYPES = {"dilemma", "belief", "inspiration", "quote", "video", "reflection"}

SUMMARIZE_SYSTEM = """你是一个笔记分类助手。分析用户给的笔记标题和正文，输出严格 JSON（不要 markdown 代码块，不要多余文字）。

分类规则：
- note_type 取值：
  - "knowledge"：技术学习、概念整理、教程、工具用法、知识总结
  - "growth"：个人成长相关，包括困境与解决方案、支撑信念、灵感启发、金句、视频笔记、自我反思
- insight_type 仅当 note_type 为 growth 时填写，knowledge 类填 null：
  - "dilemma"：面对困境时的解决方案
  - "belief"：支撑自己走过来的信念
  - "inspiration"：和别人聊天或突发启发的灵感
  - "quote"：金句、语录
  - "video"：视频内容笔记
  - "reflection"：自我反思、复盘
- summary：一句话概括笔记核心内容（不超过 50 字）
- tags：1-3 个主题标签（字符串数组）

输出格式示例：
{"note_type": "growth", "insight_type": "dilemma", "summary": "面对项目延期时通过拆解任务缓解焦虑", "tags": ["项目管理", "心态"]}
{"note_type": "knowledge", "insight_type": null, "summary": "RAG 通过检索增强生成减少幻觉", "tags": ["RAG", "LLM"]}"""


def _parse_enrichment_output(raw: str) -> dict:
    """从模型输出中提取 JSON，容错处理 markdown 代码块包裹。"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    note_type = data.get("note_type")
    if note_type not in VALID_NOTE_TYPES:
        note_type = "knowledge"
    insight_type = data.get("insight_type")
    if note_type == "knowledge" or insight_type not in VALID_INSIGHT_TYPES:
        insight_type = None
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags][:3]
    summary = str(data.get("summary", "")).strip()
    return {
        "note_type": note_type,
        "insight_type": insight_type,
        "summary": summary,
        "tags": tags,
    }


def _fallback_enrichment(note: dict) -> dict:
    """模型调用失败时的兜底：基于标题启发式判断，摘要取正文前 100 字。"""
    title = note.get("title", "")
    text = note.get("text", "")
    growth_keywords = ["困境", "信念", "灵感", "金句", "反思", "复盘", "感悟", "心态", "焦虑", "成长"]
    note_type = "growth" if any(kw in title for kw in growth_keywords) else "knowledge"
    return {
        "note_type": note_type,
        "insight_type": None,
        "summary": (text[:100] + "...") if len(text) > 100 else text,
        "tags": [],
    }


def summarize_note(note: dict) -> dict:
    """调用模型对单篇笔记做分类总结，返回 {note_type, insight_type, summary, tags}。"""
    title = note.get("title", "无标题")
    text = note.get("text", "").strip()
    content_for_model = text if text else "（正文为空，请仅根据标题分类）"
    user_msg = f"标题：{title}\n正文：{content_for_model}"

    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            extra_body=NO_THINKING,
        )
        raw = resp.choices[0].message.content
        result = _parse_enrichment_output(raw)
        if not result.get("summary"):
            result = _fallback_enrichment(note)
        return result
    except Exception:
        return _fallback_enrichment(note)


# 图片/附件类链接不进元数据。Notion 的 S3 预签名链接一条就有 1600+ 字符，
# 而且带着 X-Amz-Credential / X-Amz-Security-Token 凭证 ——
# 这些链接会被拼进每次检索的提示词，既挤爆本地模型的上下文（实测一个块
# 背 3337 字符），又是把凭证往外送的隐患。
_ASSET_URL_RE = re.compile(
    r"\.(?:png|jpe?g|gif|webp|svg|bmp|ico|pdf|zip|mp4|mov)(?:$|[?#])", re.IGNORECASE
)
_PRESIGNED_RE = re.compile(r"[?&]X-Amz-(?:Signature|Credential|Security-Token)=", re.IGNORECASE)

MAX_CITED_URLS = 3


def extract_citable_urls(raw: str) -> str:
    """从笔记正文里抽「能点回去看」的链接，返回逗号分隔的字符串。

    只留页面链接：丢掉图片/附件链接（含 Notion 的 S3 预签名链接），
    并统一去掉 query 和 fragment。
    """
    candidates = [url for _, url in re.findall(r"\[([^\]]*)\]\(([^)]+)\)", raw)]
    candidates += re.findall(r"https?://[^\s)\"'>]+", raw)

    kept: list[str] = []
    for url in candidates:
        if _ASSET_URL_RE.search(url) or _PRESIGNED_RE.search(url):
            continue
        url = url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
        if not url or url in kept:
            continue
        kept.append(url)
        if len(kept) >= MAX_CITED_URLS:
            break
    return ",".join(kept)


def strip_markdown_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://[^\s)\"\'>]+", "", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"([*_~]{1,3})(.*?)\1", r"\2", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*+]\s", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-]{3,}$", "", text, flags=re.MULTILINE)
    return text.strip()


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        if start + chunk_size >= len(text):
            chunks.append(text[start:])
            break
        end = start + chunk_size
        cut = end
        found = False
        for boundary in ['\n\n', '。', '！', '？', '\n', '，', ',', '；', ';']:
            pos = text.rfind(boundary, start, end)
            if pos != -1 and pos - start > chunk_size * 0.4:
                cut = pos + len(boundary)
                found = True
                break
        if not found:
            for punct in ['.', '!', '?']:
                pos = text.rfind(punct, start, end)
                if pos != -1 and pos - start > chunk_size * 0.4:
                    if pos > start and text[pos - 1].isdigit():
                        continue
                    cut = pos + 1
                    break
        chunks.append(text[start:cut])
        start = cut - overlap
    return chunks


def load_notes() -> list[dict]:
    """加载笔记，优先读 enriched 版本（含分类标签），无则回退到原始 notes.json。

    向后兼容：没跑过 c2_summarize.py 时，缺失的 enrichment 字段会用默认值填充。
    """
    if ENRICHED_FILE.exists():
        notes = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))
    elif NOTES_FILE.exists():
        notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"缺少 {NOTES_FILE}，请先运行 c1_pull_notes.py")
    # 兜底填充缺失的 enrichment 字段，保证下游字段一致
    for note in notes:
        note.setdefault("note_type", "knowledge")
        note.setdefault("insight_type", None)
        note.setdefault("summary", "")
        note.setdefault("tags", [])
    return notes


def build_chunks(chunk_size: int = 300, overlap: int = 50) -> list[dict]:
    notes = load_notes()
    chunks = []
    for note in notes:
        raw = note.get("text", "")
        urls = extract_citable_urls(raw)
        cleaned = strip_markdown_html(raw)
        for i, piece in enumerate(split_text(cleaned, chunk_size, overlap)):
            chunks.append(
                {
                    "chunk_id": f"{note['id']}#{i}",
                    "note_id": note["id"],
                    "title": note.get("title", ""),
                    "text": piece,
                    "note_type": note.get("note_type", "knowledge"),
                    "insight_type": note.get("insight_type") or "",
                    "summary": note.get("summary", ""),
                    "tags": note.get("tags", []),
                    "urls": urls,
                }
            )
    CHUNKS_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    return chunks


def _build_chroma_metadata(chunk: dict) -> dict:
    """构造 Chroma metadata。Chroma 的 metadata 值不支持 list，tags 转成逗号分隔字符串。"""
    tags = chunk.get("tags", [])
    tags_str = ",".join(tags) if isinstance(tags, list) else str(tags)
    return {
        "note_id": chunk["note_id"],
        "title": chunk["title"],
        "note_type": chunk.get("note_type", "knowledge"),
        "insight_type": chunk.get("insight_type", "") or "",
        "summary": chunk.get("summary", ""),
        "tags": tags_str,
        "urls": chunk.get("urls", ""),
    }


def store_chroma(chunks: list[dict] | None = None) -> int:
    """将chunks.json中的内容入库"""
    import chromadb

    if chunks is None:
        if not CHUNKS_FILE.exists():
            raise FileNotFoundError(f"缺少 {CHUNKS_FILE}，请先 build_chunks")
        chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:  # noqa: BLE001
        pass
    collection = client.create_collection(COLLECTION, embedding_function=get_embedding_function())
    if not chunks:
        return 0
    collection.add(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[_build_chroma_metadata(c) for c in chunks],
    )
    return len(chunks)
