"""
BAAI/bge-large-zh-v1.5 ONNX 版 embedding 函数。

使用 onnxruntime + tokenizers，无需 PyTorch。
模型来源：Xenova/bge-large-zh-v1.5 (Transformers.js ONNX 导出)
"""

from __future__ import annotations

import os
from typing import cast

import numpy as np
import onnxruntime as ort
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

MODEL_REPO = "Xenova/bge-large-zh-v1.5"
ONNX_FILE = "model.onnx"  # fp32 全精度, 1.3 GB

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")


class BGEOnnxEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, max_length: int = 512):
        self.max_length = max_length
        self._ensure_downloaded()

    def _ensure_downloaded(self) -> None:
        self._model_path = hf_hub_download(
            repo_id=MODEL_REPO, filename=f"onnx/{ONNX_FILE}", endpoint=HF_ENDPOINT,
        )
        self._tokenizer_path = hf_hub_download(
            repo_id=MODEL_REPO, filename="tokenizer.json", endpoint=HF_ENDPOINT,
        )
        # Also ensure config/vocab files are cached for completeness
        for f in ["config.json", "special_tokens_map.json", "tokenizer_config.json", "vocab.txt"]:
            hf_hub_download(repo_id=MODEL_REPO, filename=f, endpoint=HF_ENDPOINT)

    @property
    def _tokenizer(self) -> Tokenizer:
        if not hasattr(self, "_tok"):
            tok = Tokenizer.from_file(self._tokenizer_path)
            tok.enable_truncation(max_length=self.max_length)
            tok.enable_padding(pad_id=0, pad_token="[PAD]", length=self.max_length)
            self._tok = tok
        return self._tok

    @property
    def _session(self) -> ort.InferenceSession:
        if not hasattr(self, "_ort"):
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._ort = ort.InferenceSession(self._model_path, sess_options=opts)
        return self._ort

    def __call__(self, input: Documents) -> Embeddings:
        encoded = [self._tokenizer.encode(d) for d in input]
        input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

        onnx_input = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": np.zeros_like(input_ids, dtype=np.int64),
        }

        outputs = self._session.run(None, onnx_input)
        last_hidden = outputs[0]

        # BGE: mean pooling + L2 normalization
        mask = np.expand_dims(attention_mask.astype(np.float32), -1)
        embedding = np.sum(last_hidden * mask, axis=1) / np.maximum(np.sum(mask, axis=1), 1e-9)
        norm = np.linalg.norm(embedding, axis=1, keepdims=True)
        embedding = embedding / np.maximum(norm, 1e-12)

        return cast(Embeddings, [e.astype(np.float32) for e in embedding])
