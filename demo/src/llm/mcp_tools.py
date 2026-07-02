"""MCP 도구 ↔ OpenAI function 스키마 브리지 + 도구 실행."""
import json

_MAX_TOOL_RESULT_CHARS = 6000  # 툴 결과가 컨텍스트를 폭주시키지 않도록 절단


async def load_openai_tools(client) -> list:
    """WorkShield MCP 서버의 모든 도구를 OpenAI function-tool 스키마로 변환."""
    schemas = await client.list_tool_schemas()
    return [
        {"type": "function",
         "function": {"name": s["name"], "description": s["description"],
                      "parameters": s["input_schema"]}}
        for s in schemas
    ]


async def execute_tool_call(client, name: str, arguments_json: str) -> str:
    """모델이 요청한 도구 1건을 MCP 서버에서 실행하고 JSON 문자열 결과(절단)를 반환."""
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        args = {}
    result = await client.invoke_tool(name, args)
    return json.dumps(result, ensure_ascii=False)[:_MAX_TOOL_RESULT_CHARS]
