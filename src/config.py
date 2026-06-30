# =================================================================
# 프로젝트 전역 설정 관리 모듈
# 팀원 필독: .env 파일에 DB 연결 정보를 반드시 설정해야 합니다.
# =================================================================

import os
from dotenv import load_dotenv
from pathlib import Path

app_env = os.getenv("APP_ENV", "local")

# 1. 프로젝트 루트 경로 설정 (프로젝트 어느 위치에서든 .env·data를 찾기 위함)
# config.py 는 src/ 안에 있으므로, 프로젝트 루트는 parent.parent 입니다.
# (이 값을 기준으로 data/, .env 등을 해석하므로 src/ 가 아닌 루트여야 합니다.)
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'

# 2. .env 파일 로드
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # 기본 .env 로드 시도

OPEN_LAW_API_KEY: str | None = os.getenv('OPEN_LAW_API_KEY')
KOREAN_LAW_MCP_URL: str = os.getenv('KOREAN_LAW_MCP_URL', 'https://korean-law-mcp.fly.dev/mcp')
DB_BASE_FILE: str = os.getenv('DB_BASE_FILE', 'data/migration/contract.sqlite3')

EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "dragonkue/BGE-m3-ko")
RERANKER_MODEL_NAME: str = os.getenv("RERANKER_MODEL_NAME", "dragonkue/bge-reranker-v2-m3-ko")

# 운영(RunPod) 전용 — app_env != "local" 일 때 adapter/api_embedding_model.py 가 사용
RUNPOD_API_KEY: str | None = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID: str | None = os.getenv("RUNPOD_ENDPOINT_ID")