import logging
import asyncio
import os
from typing import List, Dict, Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class KordocCLI:
    """
    npx kordoc MCP 서버와 stdio로 통신하여 문서 변환 및 편집 작업을 위임하는 
    MCP 기반의 순수 도구 유틸리티 클래스입니다.
    """

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """비동기로 kordoc MCP 서버를 실행하여 특정 도구(Tool)를 호출합니다."""
        server_params = StdioServerParameters(
            command="npx",
            args=["kordoc", "mcp"]
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. MCP 세션 초기화
                await session.initialize()

                # 2. kordoc 툴 목록 조회 및 실제 툴 이름 매핑
                tools_result = await session.list_tools()
                actual_tool_name = tool_name

                # 목록에 매칭되는 툴 탐색 (대소문자 또는 유사성 대응)
                for tool in tools_result.tools:
                    if tool.name == tool_name:
                        actual_tool_name = tool.name
                        break
                    elif tool_name in tool.name:
                        actual_tool_name = tool.name
                        break

                # 3. 도구 실행
                result = await session.call_tool(actual_tool_name, arguments)
                if not result.content or len(result.content) == 0:
                    raise RuntimeError(f"kordoc MCP 툴 '{actual_tool_name}' 결과가 비어 있습니다.")

                return result.content[0].text

    def _run_mcp_sync(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """비동기 MCP 호출 함수를 동기식 컨텍스트로 실행할 수 있게 래핑합니다."""
        try:
            try:
                loop = asyncio.get_running_loop()
                # 이미 실행 중인 이벤트 루프가 있을 때 (예: FastMCP 서버 내부 등)
                return asyncio.run_coroutine_threadsafe(
                    self._call_mcp_tool(tool_name, arguments), loop
                ).result()
            except RuntimeError:
                # 실행 중인 이벤트 루프가 없는 일반 스레드인 경우
                return asyncio.run(self._call_mcp_tool(tool_name, arguments))
        except Exception as e:
            logging.error(f"[Error] kordoc MCP 툴 '{tool_name}' 호출 실패: {e}")
            raise RuntimeError(f"kordoc MCP 연동 오류: {e}") from e

    def parse_to_text(self, file_path: str, pages: Optional[str] = None) -> str:
        """문서에서 텍스트(마크다운 포맷)를 추출하여 문자열로 반환합니다."""
        args = {"file_path": os.path.abspath(file_path)}
        if pages:
            args["pages"] = pages
            return self._run_mcp_sync("parse_pages", args)
        return self._run_mcp_sync("parse_document", args)

    def parse_to_markdown(self, file_path: str, output_path: str, pages: Optional[str] = None) -> bool:
        """문서를 파싱하여 지정한 출력 파일로 내보냅니다."""
        # MCP 툴을 통해 마크다운 텍스트 획득
        markdown_text = self.parse_to_text(file_path, pages)
        
        # 결과를 파일로 저장
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)
            
        return os.path.exists(output_path)

    def parse_to_json(self, file_path: str, pages: Optional[str] = None) -> Dict[str, Any]:
        """문서 구조 및 메타데이터를 포함한 JSON 데이터를 반환합니다."""
        # JSON 포맷 파싱 툴 호출
        import json
        args = {"file_path": os.path.abspath(file_path)}
        # metadata 툴을 이용해 문서 요약 메타데이터를 가져옵니다.
        result_text = self._run_mcp_sync("parse_metadata", args)
        try:
            return json.loads(result_text)
        except json.JSONDecodeError as e:
            raise RuntimeError("kordoc JSON 변환 데이터 파싱 실패") from e

    def generate_hwpx(self, markdown_path: str, output_path: str, preset: Optional[str] = None) -> bool:
        """마크다운을 표준 행정 공문서 규격 HWPX 파일로 역생성합니다."""
        if not os.path.exists(markdown_path):
            raise FileNotFoundError(f"마크다운 파일을 찾을 수 없습니다: {markdown_path}")
            
        with open(markdown_path, "r", encoding="utf-8") as f:
            md_text = f.read()

        args = {
            "markdown": md_text,
            "output_path": os.path.abspath(output_path)
        }
        if preset:
            args["preset"] = preset
            
        self._run_mcp_sync("generate_document", args)
        return os.path.exists(output_path)

    def patch_hwpx(self, original_path: str, edited_markdown_path: str, output_path: str) -> bool:
        """원본 HWPX/HWP의 서식을 유지하면서 텍스트 내용만 업데이트합니다."""
        if not os.path.exists(edited_markdown_path):
            raise FileNotFoundError(f"수정된 마크다운 파일을 찾을 수 없습니다: {edited_markdown_path}")
            
        with open(edited_markdown_path, "r", encoding="utf-8") as f:
            md_text = f.read()

        args = {
            "file_path": os.path.abspath(original_path),
            "edited_markdown": md_text,
            "output_path": os.path.abspath(output_path)
        }
        self._run_mcp_sync("patch_document", args)
        return os.path.exists(output_path)

    def fill_form(
        self,
        template_path: str,
        output_path: str,
        fields: Optional[Dict[str, str]] = None,
        json_path: Optional[str] = None,
        dry_run: bool = False
    ) -> str:
        """양식 템플릿(신청서 등)의 필드 데이터 자동 바인딩을 수행합니다."""
        import json
        args = {
            "file_path": os.path.abspath(template_path)
        }
        
        target_fields = {}
        if fields:
            target_fields = fields
        elif json_path and os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                target_fields = json.load(f)
                
        args["fields"] = target_fields
        if output_path:
            args["output_path"] = os.path.abspath(output_path)
            
        return self._run_mcp_sync("fill_form", args)

    def compare_documents(self, old_path: str, new_path: str) -> str:
        """두 한글 문서 간의 차이점을 비교 분석하여 신구대조표 리포트를 반환합니다."""
        args = {
            "file_path_a": os.path.abspath(old_path),
            "file_path_b": os.path.abspath(new_path)
        }
        return self._run_mcp_sync("compare_documents", args)


# =================================================================
# 팀원 공용 kordoc CLI 유틸 객체 (Single Instance - MCP 통신 방식)
# 사용법: from adapter import kordoc
# =================================================================
kordoc = KordocCLI()
