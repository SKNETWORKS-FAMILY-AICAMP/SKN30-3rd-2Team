
import os
from dotenv import load_dotenv
from pathlib import Path

# demo/.env 를 명시적으로 로드 (루트에서 streamlit 을 실행해도 데모 전용 키를 읽도록)
_DEMO_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_DEMO_ENV if _DEMO_ENV.exists() else None)

app_env = os.getenv("APP_ENV", "local")

WORKSHIELD_MCP_URL: str = os.getenv('WORKSHIELD_MCP_URL', 'http://localhost:8000/mcp')

# ──────────────────────────────────────────────────────────────
# LLM Provider 설정 (데모 요약·질의용)
# 세 공급자 모두 OpenAI 호환 Chat Completions 로 통일 → openai SDK 하나로 처리(신규 의존성 없음).
#   openai : OpenAI 정식 API
#   gemini : Google Gemini 의 OpenAI 호환 엔드포인트
#   custom : Runpod 등에 띄운 오픈모델(vLLM/TGI) OpenAI 호환 엔드포인트
# ──────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")

CUSTOM_LLM_BASE_URL = os.getenv("CUSTOM_LLM_BASE_URL")   # 예: https://<pod-id>-8000.proxy.runpod.net/v1 (미설정 시 custom 비활성)
CUSTOM_LLM_API_KEY = os.getenv("CUSTOM_LLM_API_KEY", "EMPTY")
CUSTOM_LLM_MODEL = os.getenv("CUSTOM_LLM_MODEL")         # 서빙 중인 HF 모델 id