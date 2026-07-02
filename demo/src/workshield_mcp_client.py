import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# mcp 라이브러리 및 transport 관련 임포트
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

# config.py 에서 설정값 로드
from config import app_env, WORKSHIELD_MCP_URL



class WorkShieldMCPClient:
    """WorkShield MCP Server와 연동하여 계약서 검토 기능을 수행하는 클라이언트 클래스.
    
    APP_ENV 값에 따라 'local'일 때는 stdio 방식으로 로컬 서버 프로세스를 기동하여 연결하고,
    'prod'일 때는 Streamable HTTP 방식을 사용하여 원격/로컬 서버 엔드포인트에 접속합니다.
    """

    def __init__(self, read_timeout: Optional[float] = None):
        self.app_env = app_env
        # .env가 없거나 빈 경우 localhost:8000를 기본값으로 사용
        self.mcp_url = WORKSHIELD_MCP_URL
        self._exit_stack: Optional[AsyncExitStack] = None
        self.session: Optional[ClientSession] = None
        # 세션의 개별 요청 응답 대기 한도. None이면 mcp 기본값을 따른다.
        self._read_timeout = timedelta(seconds=read_timeout) if read_timeout else None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        """MCP 서버에 연결을 수립하고 핸드셰이크를 수행합니다."""
        self._exit_stack = AsyncExitStack()
        try:
            if self.app_env == "local":
                # 로컬 환경: stdio 통신을 위해 서브프로세스를 기동합니다.
                project_root = Path(__file__).resolve().parent.parent.parent
                app_path = project_root / "src" / "app.py"
                
                # 실행 환경 변수 복사 및 PYTHONPATH 설정
                env = os.environ.copy()
                env["PYTHONPATH"] = str(project_root / "src")
                env["MCP_TRANSPORT"] = "stdio"

                # uv를 사용하여 루트 디렉토리의 가상환경 패키지들이 제대로 로드되도록 실행
                server_params = StdioServerParameters(
                    command="uv",
                    args=["run", "--project", str(project_root), "python", str(app_path)],
                    env=env,
                )
                
                stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
                read_stream, write_stream = stdio_transport
                self.session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream, read_timeout_seconds=self._read_timeout)
                )
            else:
                # 운영/프로덕션 환경: Streamable HTTP 방식으로 서버에 연결합니다.
                http_transport = await self._exit_stack.enter_async_context(
                    streamable_http_client(self.mcp_url)
                )
                read_stream, write_stream, _ = http_transport
                self.session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream, read_timeout_seconds=self._read_timeout)
                )
            
            # MCP 핸드셰이크 수행
            await self.session.initialize()
            
        except Exception as e:
            await self.disconnect()
            raise RuntimeError(
                f"Failed to connect to WorkShield MCP Server (env={self.app_env}): {e}"
            ) from e

    async def disconnect(self):
        """연결을 안전하게 해제하고 리소스를 정리합니다."""
        if self._exit_stack:
            await self._exit_stack.aclose()
        self.session = None
        self._exit_stack = None

    def _parse_tool_response(self, response) -> Any:
        """Tool 실행 결과 응답(CallToolResult)에서 데이터를 추출하고 JSON 파싱을 시도합니다."""
        if not response or not response.content:
            return {}
        
        # 일반적으로 FastMCP는 Pydantic 모델을 JSON 문자열로 리턴합니다.
        first_content = response.content[0]
        if hasattr(first_content, "text"):
            try:
                return json.loads(first_content.text)
            except json.JSONDecodeError:
                return {"text": first_content.text}
        
        return {"content": str(response.content)}

    def _parse_resource_response(self, resource_response) -> Any:
        """Resource 읽기 결과(ReadResourceResult)에서 데이터를 추출하고 JSON 파싱을 시도합니다."""
        if not resource_response or not resource_response.contents:
            return []
            
        first_content = resource_response.contents[0]
        if hasattr(first_content, "text"):
            try:
                return json.loads(first_content.text)
            except json.JSONDecodeError:
                return first_content.text
        elif hasattr(first_content, "blob"):
            return first_content.blob
            
        return str(resource_response.contents)

    # =========================================================================
    # 🛠️ MCP Tools Wrappers
    # =========================================================================

    async def parse_contract(
        self,
        file_path: Optional[str] = None,
        file_content: Optional[str] = None,
        file_name: Optional[str] = None,
        contract_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """계약서 파일(HWP/PDF)을 조항 단위로 분해하여 반환합니다.
        
        Args:
            file_path: 로컬 파일 경로 (stdio 방식 연결 시에만 작동)
            file_content: base64 인코딩된 파일 바이너리 (HTTP 방식 연결 시 필수)
            file_name: 파일 확장자 판별용 원본 파일명 (HTTP 방식 연결 시 필수)
            contract_type: 계약 종류 (list_contract_types로 확인 가능)
        """
        args = {}
        if file_path is not None:
            args["file_path"] = file_path
        if file_content is not None:
            args["file_content"] = file_content
        if file_name is not None:
            args["file_name"] = file_name
        if contract_type is not None:
            args["contract_type"] = contract_type

        try:
            response = await self.session.call_tool("parse_contract", args)
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def match_clause(
        self,
        clause_text: str,
        contract_type: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """단일 조항 텍스트와 가장 유사한 표준조항 후보를 유사도 순으로 검색합니다."""
        args = {
            "clause_text": clause_text,
            "contract_type": contract_type,
            "top_k": top_k,
        }
        try:
            response = await self.session.call_tool("match_clause", args)
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def get_grounding(
        self,
        category: Optional[str] = None,
        clause_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """카테고리 또는 조항 본문에 해당하는 관련 법령 조문을 조회합니다."""
        args = {}
        if category is not None:
            args["category"] = category
        if clause_text is not None:
            args["clause_text"] = clause_text

        try:
            response = await self.session.call_tool("get_grounding", args)
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def review_contract(
        self,
        contract_type: str,
        file_path: Optional[str] = None,
        file_content: Optional[str] = None,
        file_name: Optional[str] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """계약서 파일 전체를 검토합니다."""
        args = {"contract_type": contract_type}
        if file_path is not None:
            args["file_path"] = file_path
        if file_content is not None:
            args["file_content"] = file_content
        if file_name is not None:
            args["file_name"] = file_name

        try:
            response = await self.session.call_tool(
                "review_contract",
                args,
                progress_callback=progress_callback,
            )
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def classify_clause(
        self,
        clause_text: str,
        contract_type: str,
        match_threshold: float = 0.5,
        change_threshold: float = 0.85,
    ) -> Dict[str, Any]:
        """단일 조항 텍스트 하나를 표준조항과 비교해 이탈 여부를 판정합니다."""
        args = {
            "clause_text": clause_text,
            "contract_type": contract_type,
            "match_threshold": match_threshold,
            "change_threshold": change_threshold,
        }
        try:
            response = await self.session.call_tool("classify_clause", args)
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def list_contract_types(self) -> Dict[str, Any]:
        """지원하는 계약 종류(contract_type) 전체 목록을 조회합니다."""
        try:
            response = await self.session.call_tool("list_contract_types")
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def list_categories(self) -> Dict[str, Any]:
        """조항 분류 카테고리(category) 전체 목록을 조회합니다."""
        try:
            response = await self.session.call_tool("list_categories")
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def list_toxic_patterns(self) -> Dict[str, Any]:
        """탐지 대상 독소조항 패턴(toxic_pattern) 전체 목록을 조회합니다."""
        try:
            response = await self.session.call_tool("list_toxic_patterns")
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    async def list_toxic_pattern_details(self) -> Dict[str, Any]:
        """독소패턴 enum → 사람이 읽는 제목 매핑용 상세 목록을 조회합니다."""
        try:
            response = await self.session.call_tool("list_toxic_pattern_details")
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    # =========================================================================
    # 🤖 LLM 툴 루프용 제네릭 도구 접근
    # =========================================================================

    async def list_tool_schemas(self) -> List[Dict[str, Any]]:
        """서버가 노출한 모든 MCP 도구를 (name, description, input_schema)로 반환 — LLM function 정의 변환용."""
        resp = await self.session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema or {"type": "object", "properties": {}},
            }
            for t in resp.tools
        ]

    async def invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """이름으로 임의 MCP 도구를 호출하고 파싱된 결과를 반환 — LLM 툴 실행 루프용."""
        try:
            response = await self.session.call_tool(name, arguments or {})
            return self._parse_tool_response(response)
        except McpError as e:
            return {"status": "ERROR", "message": f"MCP Call Failed: {e.error.message} (Code: {e.error.code})"}

    # =========================================================================
    # 📂 MCP Resources Wrappers
    # =========================================================================

    async def list_standard_clauses(self, contract_type: str) -> List[Dict[str, Any]]:
        """계약 유형별 표준조항 목록을 요약으로 읽기 전용 브라우징합니다."""
        uri = f"standard://{contract_type}"
        try:
            resource = await self.session.read_resource(uri)
            return self._parse_resource_response(resource)
        except McpError as e:
            raise RuntimeError(f"Failed to read standard clauses resource: {e.error.message}") from e

    async def get_standard_clause(self, contract_type: str, clause_id: str) -> Dict[str, Any]:
        """표준조항 원문 전체를 clause_id로 조회합니다."""
        uri = f"standard://{contract_type}/{clause_id}"
        try:
            resource = await self.session.read_resource(uri)
            return self._parse_resource_response(resource)
        except McpError as e:
            raise RuntimeError(f"Failed to read standard clause detail resource: {e.error.message}") from e


async def test_run():
    """클라이언트 동작을 테스트하는 로컬 함수"""
    print(f"--- Starting WorkShieldMCPClient Test (APP_ENV: {app_env}) ---")
    client = WorkShieldMCPClient()
    try:
        async with client:
            print("Connected to MCP Server successfully!")
            
            print("\n1. list_contract_types 호출 테스트:")
            contract_types = await client.list_contract_types()
            print(json.dumps(contract_types, indent=2, ensure_ascii=False))
            
            print("\n2. list_categories 호출 테스트:")
            categories = await client.list_categories()
            # 출력이 너무 기므로 앞부분 일부 키워드만 확인
            if "categories" in categories:
                print(f"카테고리 개수: {len(categories['categories'])}")
                print(f"첫번째 카테고리: {categories['categories'][0]}")
            else:
                print(categories)

            # 테스트용 계약 종류가 있는 경우 리소스 브라우징 테스트
            if "contract_types" in contract_types and contract_types["contract_types"]:
                test_type = contract_types["contract_types"][0]
                print(f"\n3. standard://{test_type} 리소스 조회 테스트:")
                try:
                    standards = await client.list_standard_clauses(test_type)
                    print(f"표준조항 개수: {len(standards)}")
                    if standards:
                        print(f"첫번째 표준조항 메타: {standards[0]}")
                        
                        # 상세조회 테스트
                        clause_id = standards[0].get("clause_id")
                        if clause_id:
                            print(f"\n4. standard://{test_type}/{clause_id} 상세 조회 테스트:")
                            detail = await client.get_standard_clause(test_type, clause_id)
                            print(json.dumps(detail, indent=2, ensure_ascii=False)[:300] + "...")
                except Exception as ex:
                    print(f"리소스 조회 실패 (DB에 코퍼스가 없을 수 있음): {ex}")
            
    except Exception as err:
        print(f"Test run failed with error: {err}")


if __name__ == "__main__":
    asyncio.run(test_run())
