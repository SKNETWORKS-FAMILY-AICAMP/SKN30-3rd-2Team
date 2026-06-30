# 윈도우일 때만 파워쉘을 쓰도록 기본 설정
set windows-shell := ["powershell", "-Command"]

# 도움말 출력 (메뉴판)
default:
    @just --list

# [통합 명령어] 환경 확인 및 패키지 설치
setup: check-node install-packages check-law-key uv-setup download-models migrate
    @echo ""
    @echo "🎉 모든 개발 환경 구축이 완료되었습니다!"

# ----------------------------------------------------
# 🔍 Node.js 설치 상태 확인 및 자동 설치
# ----------------------------------------------------

# 윈도우 환경 전용
[windows]
[private]
check-node:
    @echo "🔍 Node.js 설치 상태를 확인 중입니다... (OS: Windows)"
    @if (Get-Command node -ErrorAction SilentlyContinue) { echo "[OK] Node.js가 이미 설치되어 있습니다."; node -v } else { echo "[INFO] Node.js를 찾을 수 없습니다. winget으로 설치를 시작합니다..."; winget install OpenJS.NodeJS.LTS --silent --accept-source-agreements --accept-package-agreements; echo "⚠ 윈도우 환경 변수 반영을 위해 현재 터미널을 재시작한 후 'just install-packages'를 실행해 주세요."; exit 1 }

# 리눅스 / 맥(Unix 계열) 환경 전용
[unix]
[private]
check-node:
    @echo "🔍 Node.js 설치 상태를 확인 중입니다... (OS: Unix/Linux/macOS)"
    @if command -v node >/dev/null 2>&1; then echo "[OK] Node.js가 이미 설치되어 있습니다."; node -v; else echo "[INFO] Node.js를 찾을 수 없습니다. 설치를 시작합니다..."; if [ "$(uname)" = "Darwin" ]; then if command -v brew >/dev/null 2>&1; then brew install node; else echo "[ERROR] Homebrew가 필요합니다. 직접 Node.js를 설치해주세요."; exit 1; fi; else if command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y nodejs npm; elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y nodejs; else echo "[ERROR] 지원하는 패키지 관리자(apt, dnf)를 찾을 수 없습니다. 직접 node를 설치해주세요."; exit 1; fi; fi; fi

# ----------------------------------------------------
# 📦 MCP 패키지 글로벌 설치 (기설치 시 패스)
# ----------------------------------------------------

# 윈도우 환경 전용 패키지 체크 및 설치
[windows]
install-packages:
    @echo ""
    @echo "📦 MCP 글로벌 패키지 설치 상태 확인 중..."
    @if (Get-Command korean-law-mcp -ErrorAction SilentlyContinue) { echo "[OK] korean-law-mcp가 이미 설치되어 있습니다." } else { echo "[INFO] korean-law-mcp 설치 중..."; npm.cmd install -g korean-law-mcp }
    @if (Get-Command kordoc -ErrorAction SilentlyContinue) { echo "[OK] kordoc가 이미 설치되어 있습니다." } else { echo "[INFO] kordoc 설치 중..."; npm.cmd install -g kordoc pdfjs-dist }

[windows]
[private]
check-law-key:
    @$envFile = ".env"; $hasKey = $false; $apiKey = ""; if (Test-Path $envFile) { $content = Get-Content $envFile; foreach ($line in $content) { if ($line -match "^OPEN_LAW_API_KEY=(.*)") { $hasKey = $true; $apiKey = $Matches[1].Trim() } } }; if ($env:OPEN_LAW_API_KEY) { $apiKey = $env:OPEN_LAW_API_KEY; $hasKey = $true }; if (-not $hasKey) { Write-Host "🔑 법제처 API 인증키(OPEN_LAW_API_KEY)가 설정되지 않았습니다." -ForegroundColor Yellow; $inputKey = Read-Host "법제처 API 인증키(OPEN_LAW_API_KEY)를 입력해 주세요 (엔터 누르면 패스)"; if ($inputKey) { Add-Content -Path $envFile -Value "`nOPEN_LAW_API_KEY=$inputKey"; Add-Content -Path $envFile -Value "LAW_OC=$inputKey"; Write-Host "✨ .env 파일에 인증키(OPEN_LAW_API_KEY, LAW_OC)가 저장되었습니다." -ForegroundColor Green; $apiKey = $inputKey } else { Write-Host "⚠ 인증키 입력이 건너뛰어졌습니다. 추후 .env 파일에 직접 설정해 주세요." -ForegroundColor Red } } else { Write-Host "[OK] 법제처 API 인증키(OPEN_LAW_API_KEY)가 구성되어 있습니다." -ForegroundColor Green; if (Test-Path $envFile) { $content = Get-Content $envFile; if (-not ($content -match "^LAW_OC=")) { Add-Content -Path $envFile -Value "LAW_OC=$apiKey"; Write-Host "✨ .env 파일에 LAW_OC 인증키가 연동 저장되었습니다." -ForegroundColor Green } } }; if ($apiKey) { Write-Host ""; Write-Host "💡 현재 터미널 세션에 환경변수를 등록하려면 아래 명령어를 실행하세요:" -ForegroundColor Cyan; Write-Host "set LAW_OC=$apiKey           # Windows CMD" -ForegroundColor Yellow; Write-Host "`$env:LAW_OC=`"$apiKey`"       # Windows PowerShell" -ForegroundColor Yellow }

# 리눅스 / 맥(Unix 계열) 전용 패키지 체크 및 설치
[unix]
install-packages:
    @echo ""
    @echo "📦 MCP 글로벌 패키지 설치 상태 확인 중..."
    @if command -v korean-law-mcp >/dev/null 2>&1; then echo "[OK] korean-law-mcp가 이미 설치되어 있습니다."; else echo "[INFO] korean-law-mcp 설치 중..."; npm install -g korean-law-mcp; fi
    @if command -v kordoc >/dev/null 2>&1; then echo "[OK] kordoc가 이미 설치되어 있습니다."; else echo "[INFO] kordoc 설치 중..."; npm install -g kordoc pdfjs-dist; fi

[unix]
[private]
check-law-key:
    #!/usr/bin/env bash
    env_file=".env"
    has_key=false
    api_key=""
    if [ -f "$env_file" ]; then
        if grep -q "OPEN_LAW_API_KEY" "$env_file"; then
            has_key=true
            api_key=$(grep "OPEN_LAW_API_KEY" "$env_file" | cut -d'=' -f2 | tr -d '\r\n ')
        fi
    fi
    if [ -n "$OPEN_LAW_API_KEY" ]; then
        api_key="$OPEN_LAW_API_KEY"
        has_key=true
    fi
    if [ "$has_key" = false ]; then
        echo "🔑 법제처 API 인증키(OPEN_LAW_API_KEY)가 설정되지 않았습니다."
        read -p "법제처 API 인증키(OPEN_LAW_API_KEY)를 입력해 주세요 (엔터 누르면 패스): " input_key
        if [ -n "$input_key" ]; then
            echo "" >> "$env_file"
            echo "OPEN_LAW_API_KEY=$input_key" >> "$env_file"
            echo "LAW_OC=$input_key" >> "$env_file"
            echo "✨ .env 파일에 인증키(OPEN_LAW_API_KEY, LAW_OC)가 저장되었습니다."
            api_key="$input_key"
        else
            echo "⚠ 인증키 입력이 건너뛰어졌습니다. 추후 .env 파일에 직접 설정해 주세요."
        fi
    else
        echo "[OK] 법제처 API 인증키(OPEN_LAW_API_KEY)가 구성되어 있습니다."
        if [ -f "$env_file" ] && ! grep -q "LAW_OC" "$env_file"; then
            echo "LAW_OC=$api_key" >> "$env_file"
            echo "✨ .env 파일에 LAW_OC 인증키가 연동 저장되었습니다."
        fi
    fi
    if [ -n "$api_key" ]; then
        echo ""
        echo "💡 현재 터미널 세션에 환경변수를 등록하려면 아래 명령어를 실행하세요:"
        echo "export LAW_OC=$api_key"
    fi

# uv 환경이 준비되어 있는지 확인하고 가상환경을 동기화합니다.
uv-setup:
    @echo "=== Checking uv installation ==="
    uv --version

    @echo ""
    @echo "=== Syncing virtual environment and dependencies ==="
    uv sync

    @echo ""
    @echo "✨ uv 환경 점검 및 프로젝트 의존성 설치 완료!"

# uv 프로젝트 환경에서 BGE 모델 2종을 다운로드합니다. (이미 있으면 건너뜁니다)
download-models:
    @echo "=== Checking and downloading BAAI/bge-m3 ==="
    uv run hf download BAAI/bge-m3

    @echo ""
    @echo "=== Checking and downloading BAAI/bge-reranker-v2-m3 ==="
    uv run hf download BAAI/bge-reranker-v2-m3
# ----------------------------------------------------
# 🗄  DB / 인덱스 재생성 (normalize JSON/SQL = 진실의 원천)
# ----------------------------------------------------

# [통합] normalize → SQLite → Chroma 인덱스까지 전체 재생성
build-db: migrate build-index
    @echo ""
    @echo "🎉 DB / 벡터 인덱스 재생성 완료!"

# SQL 스키마 적용 + normalize JSON 적재 (SQLite 까지)
migrate:
    uv run python "src/pipe/0.migrate.py"

# normalize md to JSON
normalize:
    uv run python "src/pipe/normalize.py"

# SQLite → bge-m3 임베딩 → Chroma 인덱스 빌드 (담당: 인덱스/DB)
build-index:
    uv run python "src/pipe/build_index.py"

convert:
    uv run python "src/pipe/convert.py"

# ----------------------------------------------------
# 🚀 실행 단축키
# ----------------------------------------------------

# korean-law-mcp cli 실행
law:
    korean-law-mcp

# kordoc cli 실행
[windows]
parse file:
    @echo
    npx.cmd kordoc "{{file}}" -o 'data/02_converted/{{file_stem(file)}}.md'

[unix]
parse file:
    @echo
    npx kordoc "{{file}}" -o 'data/02_converted/{{file_stem(file)}}.md'
