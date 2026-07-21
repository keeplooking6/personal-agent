"""
D1 · 把一句话变成「向量」，亲眼看看它长啥样

运行：  python d1_embedding.py
该看到：打印出向量的维度和前几个数字。首次运行会自动下载一个很小的向量模型。

向量（embedding）是什么：把文字变成一串数字，语义相近的文字，数字也相近。
    有了它，「找相关笔记」就变成「找数字最接近的向量」，这是 RAG 的地基。

这里用 Chroma 自带的向量模型（本地、免费、开箱即用），不依赖你的 Qwen 服务是否支持 embedding。
"""

from chromadb.utils import embedding_functions

# 第一次会下载一个 ~80MB 的小模型（all-MiniLM），之后就用本地缓存
ef = embedding_functions.DefaultEmbeddingFunction()

sentences = ["我在学习 RAG", "检索增强生成是什么", "今天天气不错"]
vectors = ef(sentences)

for s, v in zip(sentences, vectors):
    print(f"『{s}』-> 向量维度 {len(v)}，前 5 个数字：{[round(x, 4) for x in v[:5]]}")

print("\n注意：前两句语义相近，它们的向量会比和第三句更接近（下一关就靠这个检索）。")
