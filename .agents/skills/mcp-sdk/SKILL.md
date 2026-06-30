---
name: mcp-sdk
description: >
  Reference for `modelcontextprotocol/python-sdk` version 1.28.1 (v1.x specification).
  Use when building or interacting with Model Context Protocol (MCP) servers and clients using FastMCP in Python.
---

Model Context Protocol (MCP) Python SDK v1.28.1 (v1.x)
======================================================

The official Python SDK for building MCP servers and clients using `FastMCP`. Version 1.28.1 conforms to the v1.x specification, where transport configurations are set in the `FastMCP` constructor and exceptions inherit from `McpError`.

Installation
------------

```bash
pip install "mcp[cli]>=1.28.1"
```

Server Implementation (`FastMCP`)
---------------------------------

`FastMCP` is the high-level framework to build MCP servers quickly. It parses docstrings and type annotations to generate schemas automatically.

### 1. Basic Server Setup

```python
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("WorkShield")

# 1. Registering a Tool
@mcp.tool()
def parse_contract(file_path: str, contract_type: Optional[str] = None) -> dict:
    """
    계약서 파일(HWP/PDF)을 조항 단위로 분해하여 반환합니다.

    Args:
        file_path: 분석할 계약서 파일의 절대 경로.
        contract_type: 계약 종류 컨텍스트 (SW_FREELANCE / SW_EMPLOYMENT).
    """
    # implementation details...
    return {"status": "OK", "clauses": []}

# 2. Registering a Resource (Dynamic URI)
@mcp.resource("contract://template/{name}")
def get_template(name: str) -> str:
    """
    표준 계약서 템플릿의 본문을 가져옵니다.
    """
    return f"Standard contract template content for {name}"

# 3. Registering a Prompt Template
@mcp.prompt()
def review_prompt(contract_text: str) -> str:
    """
    계약서 검토를 요청하는 프롬프트 템플릿을 생성합니다.
    """
    return f"다음 계약서의 불리한 조항을 검토해주세요:\n\n{contract_text}"

# Running the Server (Defaults to stdio transport)
if __name__ == "__main__":
    mcp.run()
```

### 2. Transport Configurations (v1.x Specification)

In v1.x, transport-specific options (host, port, sse_path, json_response, etc.) are passed **directly to the `FastMCP` constructor**, not to the `.run()` method.

#### Stdio Transport (Default)
```python
mcp = FastMCP("Demo")
mcp.run() # runs on stdio
```

#### SSE (Server-Sent Events) Transport
```python
mcp = FastMCP("Server", host="0.0.0.0", port=9000, sse_path="/events")
mcp.run(transport="sse")
```

#### Streamable HTTP Transport
```python
mcp = FastMCP("Demo", json_response=True, stateless_http=True)
mcp.run(transport="streamable-http")
```

---

Client Implementation & Exceptions
----------------------------------

### 1. Exception Handling (v1.x `McpError`)

In v1.x, errors related to MCP communications are raised as `McpError` (Capitalized as `McpError` in v1, changed to `MCPError` in v2).

```python
from mcp.shared.exceptions import McpError

try:
    result = await session.call_tool("parse_contract", {"file_path": "a.pdf"})
except McpError as e:
    # In v1, access the error details via e.error.message
    print(f"MCP Call Failed: {e.error.message} (Code: {e.error.code})")
```

### 2. Standard Client Setup (Stdio Connection)

```python
import asyncio
import os
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_client():
    server_params = StdioServerParameters(
        command="python",
        args=["src/server/server.py"],
        env=os.environ.copy()
    )
    
    async with AsyncExitStack() as exit_stack:
        # Establish transport and session
        stdio_transport = await exit_stack.enter_async_context(stdio_client(server_params))
        read_stream, write_stream = stdio_transport
        session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        
        # Initialize handshake
        await session.initialize()
        
        # Call tool
        response = await session.call_tool("parse_contract", {"file_path": "data/contract.pdf"})
        print("Response:", response.content)

if __name__ == "__main__":
    asyncio.run(run_client())
```

---

Debugging and Testing
---------------------

### 1. Using MCP Inspector
You can test the stdio server interactively by calling:
```bash
npx @modelcontextprotocol/inspector uv run python src/server/server.py
```
*(Note: Ensure all required environment variables are set in the inspector execution environment if needed.)*
