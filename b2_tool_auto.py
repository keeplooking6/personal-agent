"""
B2 · 让模型自己决定调用工具（function calling）

运行：  python b2_tool_auto.py
该看到：模型自己判断「这个问题需要算数」，返回一个工具调用请求；
        我们的代码执行计算并回填，模型再给出最终答案。

和 B1 的区别：B1 是我们手动决定用工具；B2 是把工具「声明」给模型，
           由模型自己决定要不要用、用哪个、传什么参数。这就是 function calling。

注意：需要你的 llama.cpp/Qwen 服务开启了工具调用支持。若模型没有触发工具调用，
     多半是服务端未开启该能力，可先跳过这一关，B3/B4 用 MCP 不受影响。
"""

import json

from common import QWEN_MODEL, NO_THINKING, get_client

client = get_client()


def calculate(expression: str) -> str:
    """一个简单的计算器工具。eval 仅用于教学演示，生产别这么写。"""
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:  # noqa: BLE001
        return f"计算出错: {e}"


# 用 OpenAI 的标准格式，把工具「声明」给模型：它叫什么、干什么、需要什么参数
tools = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算一个数学表达式，比如 (12+8)*3",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式"}
                },
                "required": ["expression"],
            },
        },
    }
]

messages = [
    {"role": "system", "content": "你是一个助手，遇到算数就用 calculate 工具。"},
    {"role": "user", "content": "帮我算一下 (12 + 8) * 3 等于多少？"},
]

# 第一次请求：模型看到工具，决定是否调用
resp = client.chat.completions.create(
    model=QWEN_MODEL, messages=messages, tools=tools, extra_body=NO_THINKING
)
msg = resp.choices[0].message

# 由模型决定要不要调用工具，用哪个、传什么参数。
if msg.tool_calls:
    # 模型决定调用工具了。把它的决定加进历史
    messages.append(msg)
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)
        print(f"[模型想调用 {call.function.name}，参数 = {args}]")
        result = calculate(**args)
        print(f"[我们执行后结果 = {result}]\n")
        # 把工具结果回填给模型（role=tool，用 tool_call_id 对应上）
        messages.append(
            {"role": "tool", "tool_call_id": call.id, "content": result}
        )

    # 第二次请求：模型拿到工具结果，给出最终自然语言答案
    final = client.chat.completions.create(
        model=QWEN_MODEL, messages=messages, extra_body=NO_THINKING
    )
    print("AI：", final.choices[0].message.content)
else:
    print("模型没有触发工具调用，直接回答：", msg.content)
