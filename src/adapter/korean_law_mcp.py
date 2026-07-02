import logging
from typing import Dict, Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from adapter.async_bridge import run_coroutine_blocking

class KoreanLawMCPClient:
    """
    korean-law MCP 서버와 stdio로 통신하여 법령 및 판례 검색/리서치 작업을 수행하는 
    MCP 기반의 순수 도구 유틸리티 클래스입니다.
    """

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """비동기로 korean-law MCP 서버를 실행하여 특정 도구(Tool)를 호출합니다."""
        # 전역 설치된 'korean-law' 명령어를 활용하여 MCP stdio 연결을 확립합니다.
        server_params = StdioServerParameters(
            command="korean-law",
            args=[]
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. MCP 세션 초기화
                await session.initialize()

                # 2. 제공 툴 목록 조회 및 실제 툴 이름 매핑
                tools_result = await session.list_tools()
                actual_tool_name = tool_name

                # 목록에 매칭되는 툴 탐색
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
                    raise RuntimeError(f"korean-law MCP 툴 '{actual_tool_name}' 결과가 비어 있습니다.")

                return result.content[0].text

    def _run_mcp_sync(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """비동기 MCP 호출 함수를 동기식 컨텍스트로 실행할 수 있게 래핑합니다.

        FastMCP 서버의 이벤트 루프를 블로킹하지 않도록, 실행 중인 루프가 있으면 별도
        스레드의 새 루프에서 실행한다(async_bridge 참고 — 데드락 방지).
        """
        try:
            return run_coroutine_blocking(self._call_mcp_tool(tool_name, arguments))
        except Exception as e:
            logging.error(f"[Error] korean-law MCP 툴 '{tool_name}' 호출 실패: {e}")
            raise RuntimeError(f"korean-law MCP 연동 오류: {e}") from e

    def query(self, query_str: str) -> str:
        """자연어 질문 또는 조문을 받아 직접 법률 검색을 처리합니다."""
        return self._run_mcp_sync("query", {"query": query_str})

    def search_law(self, query: str) -> str:
        """특정 법령명을 키워드로 정밀 검색합니다."""
        return self._run_mcp_sync("search_law", {"query": query})

    def cite_check(self, case_number: str) -> str:
        """특정 판례 번호의 인용 유효성 및 폐기 여부를 체크합니다."""
        return self._run_mcp_sync("cite_check", {"caseNumber": case_number})

    def legal_research(self, query: str, task: str = "full_research") -> str:
        """
        다단계 종합 법률 리서치 서비스를 실행합니다.
        
        Tasks:
            - 'full_research': 종합 리서치 (AI 검색 -> 법령 -> 판례 -> 해석례)
            - 'law_system': 법체계 파악 (3단 비교 및 조문 일괄 조회)
            - 'action_basis': 행정 처분/허가 근거 확인
            - 'procedure_detail': 별표 및 관련 서식 추출
        """
        return self._run_mcp_sync("legal_research", {"query": query, "task": task})

    def legal_analysis(self, mode: str, **kwargs) -> str:
        """
        정밀 분석 및 조문 환각 방지 검증 모드를 실행합니다.
        
        Modes:
            - 'verify_citations': 에이전트 답변 내 조문 인용의 실제 존재 여부 검증 (환각 방지)
            - 'cite_check': 전원합의체 판결 변경/폐기 여부 확인
            - 'applicable_law': 특정 기준 시행일의 행위시법 판단 및 부칙 비교
        """
        args = {"mode": mode}
        args.update(kwargs)
        return self._run_mcp_sync("legal_analysis", args)


# =================================================================
# 팀원 공용 korean-law MCP 유틸 객체 (Single Instance)
# 사용법: from adapter import koreanLaw
# =================================================================
koreanLaw = KoreanLawMCPClient()
