"""
C4 · 入库时总结：为每篇笔记生成 summary / tags / note_type / insight_type

运行：  python c2_summarize.py
        python c2_summarize.py --force   # 忽略增量，重新处理所有笔记
前提：  先跑过 c1_pull_notes.py，已有 data/notes.json。
该看到：打印每篇笔记的分类结果，并生成 data/notes_enriched.json。
下游：  c3_chunk.py / d2_store_chroma.py 自动读取 enriched 数据，
        chunk metadata 携带 note_type / insight_type / summary / tags，
        d3/d4 检索时可按类型过滤。

为什么需要这一步：
    纯向量检索只能按语义相似度找笔记，无法区分「知识笔记」和「成长型笔记」。
    本关在入库前让模型给每篇笔记打上结构化标签：
      - note_type:    knowledge（知识学习）/ growth（成长洞察）
      - insight_type: growth 类细分：dilemma/belief/inspiration/quote/video/reflection
      - summary:      一句话摘要，用于 L2 卡片层
      - tags:         主题标签，用于后续聚类
    这些字段塞进 Chroma metadata，检索时可按类型过滤——这是「分门别类」的基础。

增量处理：已处理过的 note_id 会跳过，避免重复调用模型。
    用 --force 可强制重新处理全部笔记。
"""

import json
import sys
from pathlib import Path

from pipeline import (
    ENRICHED_FILE,
    NOTES_FILE,
    summarize_note,
)

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_existing_enriched() -> dict:
    """加载已有的 enrichment 结果，返回 {note_id: enrichment} 映射。"""
    if not ENRICHED_FILE.exists():
        return {}
    try:
        data = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))
        return {item["id"]: item for item in data}
    except (json.JSONDecodeError, KeyError):
        return {}


def main() -> None:
    force = "--force" in sys.argv

    if not NOTES_FILE.exists():
        print("没找到 notes.json，请先运行 c1_pull_notes.py")
        return

    notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    existing = {} if force else load_existing_enriched()

    enriched = []
    new_count = 0
    skipped_count = 0

    for note in notes:
        note_id = note["id"]
        # TODO：不只是note_id已存在于existing中就可以跳过不执行，原本的数据内容也会有更新
        if note_id in existing:
            enriched.append(existing[note_id])
            skipped_count += 1
            continue

        print(f"正在处理：{note.get('title', note_id)}")
        enrichment = summarize_note(note)
        enriched_note = {
            **note,
            "note_type": enrichment["note_type"],
            "insight_type": enrichment["insight_type"],
            "summary": enrichment["summary"],
            "tags": enrichment["tags"],
        }
        enriched.append(enriched_note)
        new_count += 1
        print(f"  -> note_type={enrichment['note_type']}, "
              f"insight_type={enrichment['insight_type']}, "
              f"tags={enrichment['tags']}")

    ENRICHED_FILE.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n处理完成：新增 {new_count} 篇，跳过 {skipped_count} 篇")
    print(f"已保存到 {ENRICHED_FILE}")

    type_dist = {}
    for item in enriched:
        nt = item.get("note_type", "unknown")
        type_dist[nt] = type_dist.get(nt, 0) + 1
    print(f"分类分布：{type_dist}")


if __name__ == "__main__":
    main()
