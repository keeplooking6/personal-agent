"""
B3 · 连上 Notion MCP，列出所有可用工具，并保存到 data/mcp_tools.json

运行：  python b3_mcp_list_tools.py
前提：  你的 Notion MCP 服务已经在 localhost:8000 跑着（和现有项目一样）。
该看到：打印出 Notion MCP 提供的所有工具名字和说明，并保存到 data/mcp_tools.json。

MCP 是什么：一个「工具市场」的标准协议。你的 Notion MCP 服务把「操作 Notion 的能力」
           打包成一组工具，任何懂 MCP 的程序（包括这里的 Python）都能连上来用。
           你现有的 TS 项目就是这么用的，这一关我们用 Python 走一遍。

MCP 客户端是异步的，所以代码用了 async/await，跟着抄即可，不用纠结细节。
"""

import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from common import MCP_TOKEN, MCP_URL

DATA_FILE = Path(__file__).resolve().parent / "data" / "mcp_tools.json"


async def main() -> None:
    headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

            tools = []
            print(f"Notion MCP 一共提供了 {len(result.tools)} 个工具：\n")
            for t in result.tools:
                tools.append({
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                })
                print(f"- {t.name}: {t.description}")

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已保存到 {DATA_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
