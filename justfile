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
    @echo "=== Checking and downloading dragonkue/BGE-m3-ko ==="
    uv run hf download dragonkue/BGE-m3-ko

    @echo ""
    @echo "=== Checking and downloading dragonkue/bge-reranker-v2-m3-ko ==="
    uv run hf download dragonkue/bge-reranker-v2-m3-ko
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
# eval & test
# ----------------------------------------------------

# 평가 드라이버 실행 (예: just eval, just eval b, just eval a v2, 환경 분기는 env="prod" 등으로 지정)
eval track="a" version="" env="local":
    APP_ENV={{env}} PYTHONPATH=src uv run python -m eval.run_eval {{track}} {{version}}

# 테스트 실행 (type: unit (기본), integration, all)
test type="unit":
    #!/usr/bin/env bash
    set -e
    case "{{type}}" in
        unit)
            echo "Running Unit Tests (excluding integration)..."
            uv run pytest
            ;;
        integration)
            echo "Running Integration Tests (requiring external DB/models)..."
            uv run pytest -m "integration"
            ;;
        all)
            echo "Running All Tests (Unit + Integration)..."
            uv run pytest -m "integration or not integration"
            ;;
        *)
            echo "Error: Invalid test type '{{type}}'. Choose from: unit, integration, all"
            exit 1
            ;;
    esac
 

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

# MCP 서버 실행 (transport: stdio, sse, streamable-http / port: 바인딩할 포트 번호)
run-mcp transport="stdio" port="8000":
    PYTHONPATH=src MCP_TRANSPORT={{transport}} MCP_PORT={{port}} uv run python src/app.py

# MCP Inspector 웹 테스트 UI 실행 (.env 환경변수 및 PYTHONPATH 로드)
run-mcp-ui:
    #!/usr/bin/env bash
    set -e
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | xargs)
    fi
    PYTHONPATH=src npx @modelcontextprotocol/inspector uv run python src/app.py

# ----------------------------------------------------
# Runpod
# ----------------------------------------------------

# Runpod CLI 설치 및 상태 점검 (OS 자동 판별)
install-runpod:
    #!/usr/bin/env bash
    set -e
    if ! command -v runpodctl &> /dev/null; then
        echo "runpodctl CLI가 설치되어 있지 않습니다. OS에 맞게 설치를 진행합니다..."
        OS_TYPE="$(uname -s)"
        case "${OS_TYPE}" in
            Darwin*)
                echo "Detecting macOS: Installing via Homebrew..."
                brew install runpod/runpodctl/runpodctl
                ;;
            Linux*)
                echo "Detecting Linux: Downloading and copying to /usr/bin/runpodctl..."
                wget --quiet --show-progress https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-linux-amd64 -O runpodctl
                chmod +x runpodctl
                sudo cp runpodctl /usr/bin/runpodctl
                rm runpodctl
                ;;
            CYGWIN*|MINGW*|MSYS*)
                echo "Detecting Windows: Downloading runpodctl-windows-amd64.exe..."
                wget https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-windows-amd64.exe -O runpodctl.exe
                mv runpodctl.exe runpodctl
                chmod +x runpodctl
                alias runpodctl="./runpodctl"
                ;;
            *)
                echo "Error: 알 수 없는 OS 타입($OS_TYPE)입니다. 직접 runpodctl을 설치해 주세요."
                exit 1
                ;;
        esac
    else
        echo "[OK] runpodctl CLI가 이미 설치되어 있습니다."
    fi

    echo "Running runpodctl doctor..."
    runpodctl doctor

# [최초 1회 실행] Runpod에 임베딩/리랭킹 모델 서빙용 템플릿 및 서버리스 엔드포인트를 생성하고, .env의 RUNPOD_ENDPOINT_ID를 자동 갱신합니다.
deploy-embedding: install-runpod
    #!/usr/bin/env bash
    set -e

    echo "Creating Runpod template..."
    OUT=$(runpodctl template create --name workshield-embed-rerank --image ghcr.io/hong1008/workshield-embed-rerank:latest --serverless)
    echo "$OUT"

    # JSON 출력에서 "id" 키의 값을 안전하게 파싱 (jq 설치 여부와 무관하도록 python3 활용)
    TEMPLATE_ID=$(echo "$OUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")
    if [ -z "$TEMPLATE_ID" ]; then
        echo "Error: Failed to extract Template ID from runpodctl JSON output."
        exit 1
    fi
    echo "Successfully extracted Template ID: $TEMPLATE_ID"


    echo "Creating Runpod Serverless endpoint..."
    SLS_OUT=$(runpodctl serverless create \
        --name workshield-embed-rerank \
        --template-id "$TEMPLATE_ID" \
        --gpu-id "NVIDIA RTX A4000" \
        --workers-min 0 --workers-max 1 --idle-timeout 60)
    echo "$SLS_OUT"

    ENDPOINT_ID=$(echo "$SLS_OUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")
    if [ -z "$ENDPOINT_ID" ]; then
        echo "Error: Failed to extract Endpoint ID from runpodctl JSON output."
        exit 1
    fi
    echo "Successfully extracted RUNPOD_ENDPOINT_ID: $ENDPOINT_ID"

    # .env 파일 내 RUNPOD_ENDPOINT_ID 값 갱신 (없으면 추가, 있으면 치환)
    if [ -f ".env" ]; then
        if grep -q "^RUNPOD_ENDPOINT_ID=" .env; then
            sed -i "s/^RUNPOD_ENDPOINT_ID=.*/RUNPOD_ENDPOINT_ID='$ENDPOINT_ID'/" .env
        else
            echo "RUNPOD_ENDPOINT_ID='$ENDPOINT_ID'" >> .env
        fi
        echo "Updated .env with RUNPOD_ENDPOINT_ID='$ENDPOINT_ID'"
    else
        echo "RUNPOD_ENDPOINT_ID='$ENDPOINT_ID'" > .env
        echo "Created .env with RUNPOD_ENDPOINT_ID='$ENDPOINT_ID'"
    fi


# Runpod 임베딩/리랭커 워커 활성화 (웜업 - workers-min 1)
embed-on:
    #!/usr/bin/env bash
    set -e
    if [ -f ".env" ]; then
        ENDPOINT_ID=$(grep "^RUNPOD_ENDPOINT_ID=" .env | cut -d'=' -f2 | tr -d "'\"")
    fi
    if [ -z "$ENDPOINT_ID" ]; then
        echo "Error: RUNPOD_ENDPOINT_ID가 .env에 설정되어 있지 않습니다."
        exit 1
    fi
    echo "Warming up Runpod Serverless endpoint ($ENDPOINT_ID)..."
    runpodctl serverless update "$ENDPOINT_ID" --workers-min 1

# Runpod 임베딩/리랭커 워커 비활성화 (과금 방지 - workers-min 0)
embed-off:
    #!/usr/bin/env bash
    set -e
    if [ -f ".env" ]; then
        ENDPOINT_ID=$(grep "^RUNPOD_ENDPOINT_ID=" .env | cut -d'=' -f2 | tr -d "'\"")
    fi
    if [ -z "$ENDPOINT_ID" ]; then
        echo "Error: RUNPOD_ENDPOINT_ID가 .env에 설정되어 있지 않습니다."
        exit 1
    fi
    echo "Cooling down Runpod Serverless endpoint ($ENDPOINT_ID)..."
    runpodctl serverless update "$ENDPOINT_ID" --workers-min 0


# ----------------------------------------------------
# 🐳 Docker 배포 (Node+Python 런타임, sqlite/chroma 스냅샷 포함, 임베딩/리랭커 모델 제외)
# ----------------------------------------------------

docker_image := "workshield-mcp"

# 이미지 빌드 (data/03_normalized, data/migration/*.sqlite3 를 COPY — 최신 상태로 갱신하려면 먼저 `just build-db`)
docker-build:
    docker build -t {{docker_image}} .

# 포그라운드 실행 (streamable-http :8000). .env의 RUNPOD_API_KEY/RUNPOD_ENDPOINT_ID/OPEN_LAW_API_KEY 필요
docker-run: docker-build
    docker run --rm -it \
        --env-file .env \
        -e APP_ENV=prod \
        -p 8000:8000 \
        --name {{docker_image}} \
        {{docker_image}}

# 백그라운드 실행
docker-up: docker-build
    docker run -d \
        --env-file .env \
        -e APP_ENV=prod \
        -p 8000:8000 \
        --name {{docker_image}} \
        {{docker_image}}

# 백그라운드 컨테이너 중지 및 제거
docker-down:
    docker rm -f {{docker_image}}
