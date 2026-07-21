"""
J1 · Personal Agent HTTP 服务

启动：  uvicorn j1_api:app --reload --port 8010
测试：  http://localhost:8010/docs

阶段 6：接入 agent_core 编排器，支持 chat / rag / tool / auto 路由。
"""

from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_core import AgentCore
from observe import TraceLogger

app = FastAPI(title="Personal Knowledge Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

core = AgentCore()


class ChatIn(BaseModel):
    message: str
    mode: Literal["auto", "chat", "rag", "tool"] = "auto"
    top_k: int = Field(default=3, ge=1, le=10)


@app.get("/")
def health() -> dict:
    return {
        "ok": True,
        "msg": "Personal Knowledge Agent 已启动",
        "endpoints": ["/api/agent/chat", "/api/py-chat"],
    }


@app.post("/api/agent/chat")
async def agent_chat(body: ChatIn) -> dict:
    trace = TraceLogger()
    result = await core.run(body.message, mode=body.mode, top_k=body.top_k, trace=trace)
    trace.print_summary()
    return {"reply": result.get("answer", ""), **result, "trace": trace.summary()}


@app.post("/api/py-chat")
async def py_chat(body: ChatIn) -> dict:
    """兼容旧接口：默认 auto 路由。"""
    return await agent_chat(body)


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}
