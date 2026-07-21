"""
可观测性工具：结构化 trace 日志，供 b4/d4/agent_core 复用。

H1 演示了「打印耗时和 token」；这里封装成可复用的 TraceLogger，
让 Agent Loop 和 RAG 路径都能输出 step-by-step trace。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceStep:
    step: int
    kind: str  # llm | tool | retrieve | route
    name: str
    elapsed_s: float
    prompt_tokens: int | str = "?"
    completion_tokens: int | str = "?"
    total_tokens: int | str = "?"
    detail: dict[str, Any] = field(default_factory=dict)


class TraceLogger:
    """收集一次请求的 trace，支持打印和导出 JSON。"""

    def __init__(self, request_id: str = "") -> None:
        self.request_id = request_id or f"req-{int(time.time())}"
        self.steps: list[TraceStep] = []
        self._step_counter = 0

    def log_llm(self, name: str, resp: Any, elapsed_s: float, **detail: Any) -> None:
        usage = getattr(resp, "usage", None)
        self._step_counter += 1
        self.steps.append(
            TraceStep(
                step=self._step_counter,
                kind="llm",
                name=name,
                elapsed_s=elapsed_s,
                prompt_tokens=getattr(usage, "prompt_tokens", "?") if usage else "?",
                completion_tokens=getattr(usage, "completion_tokens", "?") if usage else "?",
                total_tokens=getattr(usage, "total_tokens", "?") if usage else "?",
                detail=detail,
            )
        )
        print(
            f"[trace {self.request_id}] step {self._step_counter} llm/{name} "
            f"{elapsed_s:.2f}s tokens={self.steps[-1].total_tokens}"
        )

    def log_tool(self, name: str, args: dict, result_chars: int, elapsed_s: float) -> None:
        self._step_counter += 1
        self.steps.append(
            TraceStep(
                step=self._step_counter,
                kind="tool",
                name=name,
                elapsed_s=elapsed_s,
                detail={"args": args, "result_chars": result_chars},
            )
        )
        print(
            f"[trace {self.request_id}] step {self._step_counter} tool/{name} "
            f"{elapsed_s:.2f}s result_chars={result_chars}"
        )

    def log_retrieve(self, query: str, k: int, hit_count: int, elapsed_s: float) -> None:
        self._step_counter += 1
        self.steps.append(
            TraceStep(
                step=self._step_counter,
                kind="retrieve",
                name="chroma_query",
                elapsed_s=elapsed_s,
                detail={"query": query, "top_k": k, "hit_count": hit_count},
            )
        )
        print(
            f"[trace {self.request_id}] step {self._step_counter} retrieve top_k={k} "
            f"hits={hit_count} {elapsed_s:.2f}s"
        )

    def log_route(self, route: str, reason: str) -> None:
        self._step_counter += 1
        self.steps.append(
            TraceStep(
                step=self._step_counter,
                kind="route",
                name=route,
                elapsed_s=0.0,
                detail={"reason": reason},
            )
        )
        print(f"[trace {self.request_id}] route -> {route} ({reason})")

    def summary(self) -> dict[str, Any]:
        total_elapsed = sum(s.elapsed_s for s in self.steps)
        llm_steps = [s for s in self.steps if s.kind == "llm"]
        tool_steps = [s for s in self.steps if s.kind == "tool"]
        return {
            "request_id": self.request_id,
            "total_steps": len(self.steps),
            "llm_calls": len(llm_steps),
            "tool_calls": len(tool_steps),
            "total_elapsed_s": round(total_elapsed, 3),
            "steps": [asdict(s) for s in self.steps],
        }

    def print_summary(self) -> None:
        s = self.summary()
        print(
            f"\n[trace 汇总] {s['request_id']} | "
            f"steps={s['total_steps']} llm={s['llm_calls']} tool={s['tool_calls']} "
            f"elapsed={s['total_elapsed_s']}s"
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, ensure_ascii=False, indent=2)


def timed_call(fn, *args, **kwargs):
    """执行函数并返回 (result, elapsed_seconds)。"""
    start = time.time()
    result = fn(*args, **kwargs)
    return result, time.time() - start
