import os
import sys

# 프로젝트 루트와 src 디렉토리를 Python 모듈 검색 경로(sys.path)에 자동으로 추가합니다.
# 이 파일(src/app.py)은 src 디렉토리 바로 밑에 있으므로 현재 디렉토리가 src 디렉토리가 됩니다.
current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from server.server import mcp

if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] [%(levelname)s] (%(filename)s:%(lineno)d) %(message)s"
    )

    # 로컬 개발: 기본 stdio. 컨테이너 배포: MCP_TRANSPORT=streamable-http (Dockerfile 참고)
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        mcp.settings.host = os.getenv("MCP_HOST", mcp.settings.host)
        mcp.settings.port = int(os.getenv("MCP_PORT", mcp.settings.port))
    mcp.run(transport=transport)
