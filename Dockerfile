# =================================================================
# WorkShield MCP 서버 이미지
# - Python(uv) + Node.js(kordoc, korean-law-mcp CLI) 런타임
# - data/03_normalized(정답) · data/migration(SQLite+Chroma 스냅샷) 포함
# - 임베딩/리랭커 로컬 모델은 제외 (APP_ENV=prod → RunPod API 사용, adapter/__init__.py 참고)
# =================================================================
FROM python:3.13-slim

# Node.js 22.x (korean-law-mcp 요구사항 >=20.19, kordoc 요구사항 >=18)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g korean-law-mcp kordoc pdfjs-dist \
    && apt-get purge -y curl gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /uvx /usr/local/bin/

WORKDIR /app

# 의존성 레이어 캐싱: 소스 변경과 무관하게 의존성만 먼저 설치
# (sentence-transformers 등 dev 그룹은 제외 → 임베딩/리랭커 로컬 모델 미포함)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY data/03_normalized/ ./data/03_normalized/
COPY data/migration/ ./data/migration/

RUN uv sync --frozen --no-dev

ENV APP_ENV=prod \
    PATH="/app/.venv/bin:$PATH" \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

# RUNPOD_API_KEY / RUNPOD_ENDPOINT_ID / OPEN_LAW_API_KEY 는 런타임에 --env-file 등으로 주입
CMD ["python", "src/app.py"]
