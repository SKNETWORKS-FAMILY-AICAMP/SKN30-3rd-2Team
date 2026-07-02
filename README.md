# WorkShield 🛡️

> **프리랜서 용역계약서를 표준계약서와 조항 단위로 비교해 "표준 대비 이탈"을 탐지하는 RAG MCP 시스템**

내가 받은 계약서가 정부·공공기관 **표준계약서** 대비 **어디가 빠졌고(누락) / 더 들어갔고(추가) / 다르게 쓰였는지(변경)** 를 찾아주고, 관련 **법령 조문**까지 근거로 붙여줍니다.

## 핵심 명제

**"올바른 법 해석을 생성"하지 않는다. "표준 대비 이탈을 탐지"한다.**

법 해석을 AI가 지어내면 정답 기준이 무너지고 책임 문제가 생깁니다. 그래서 **표준계약서를 정답(기준)으로 고정**하고, 사용자 조항이 그 기준에서 벗어난 지점을 검색으로 찾습니다. "벗어남"은 검증·측정이 가능한 문제입니다.

- **1차 MVP (현재):** LLM 없이 **검색·비교·규칙**만으로 이탈 탐지 → MCP 도구로 제공. LLM 없이 정량 평가(Recall@k·MRR·ablation).
- **2차 (예정):** 1차 MCP를 LLM에 붙인 웹앱 — "불리함" 해석·협상 초안 생성.

> 자세한 기획은 [docs/01.mvp_기획.md](docs/01.mvp_기획.md) 참고.

---

## 빠른 시작

### 사전 준비물
- [uv](https://docs.astral.sh/uv/) (Python 패키지 매니저), Python 3.13
- Node.js (없으면 `just setup`이 자동 설치 시도)
- 법제처 API 인증키 `OPEN_LAW_API_KEY` ([open.law.go.kr](https://open.law.go.kr) 발급) — `just setup` 중 입력 안내

### 설치 & 빌드
```bash
uv tool install rust-just     # just 명령 러너 설치 (최초 1회)
just setup                    # node·MCP패키지·uv동기화·모델다운로드·DB마이그레이션 일괄
just build-db                 # 03_normalized(정답) → SQLite → Chroma 인덱스 재생성
```

### 주요 명령
| 명령 | 설명 |
| --- | --- |
| `just setup` | 최초 1회: node·MCP·uv·모델 다운로드 |
| `just install-runpod` | Runpod CLI 설치 및 상태 점검 (OS 자동 판별) |
| `just build-db` | [통합] normalize → SQLite → Chroma 인덱스 재생성 |
| `just migrate` | SQLite 마이그레이션까지만 실행 |
| `just test` | 단위 테스트 실행 (integration 제외) |
| `just test [type]` | 테스트 유형 선택 실행 (unit, integration, all) |
| `just eval [t] [v] [e]` | 평가 드라이버 실행 (t: a/b, v: 골든버전, e: local/prod) |
| `just run-mcp [t] [p]` | MCP 서버 로컬 실행 (t: stdio/sse/streamable-http, p: 포트) |
| `just run-mcp-ui` | MCP Inspector 웹 테스트 UI 실행 (.env 바인딩) |
| `just deploy-embedding` | [최초 1회] Runpod 템플릿/서버리스 생성 및 .env 갱신 |
| `just embed-on` | Runpod 서버리스 워커 웜업 (min_workers=1) |
| `just embed-off` | Runpod 서버리스 워커 과금 차단 (min_workers=0) |
| `just docker-build` | Docker 이미지 빌드 |
| `just docker-run` | 로컬 Docker 포그라운드 실행 (streamable-http 8000포트 서빙) |

---

## 아키텍처

**헥사고날(포트-어댑터) 구조 — 코어는 외부를 모른다.** 동결된 계약(`contracts`)에만 의존해 여러 명이 병렬로 개발합니다.

```mermaid
flowchart TD
    subgraph 동결["contracts (단일 진실원)"]
        E[enums · models · ports]
    end
    CORE[core<br/>이탈 탐지 순수 함수] --> 동결
    ADP[adapter<br/>DB·임베딩·검색·법령 MCP] --> 동결
    PIPE[pipe<br/>오프라인 빌드 + 런타임 검토] --> CORE
    PIPE --> ADP
    MCP[mcp_server / demo] --> PIPE
```

### 런타임 검토 흐름 (review_contract)
```mermaid
flowchart LR
    A[계약서 업로드<br/>PDF/HWP] --> B[조항 분해<br/>제N조 단위]
    B --> C[하이브리드 검색<br/>Chroma+BM25]
    C --> D[리랭커<br/>매칭 정밀화]
    D --> E[이탈 분류<br/>누락·추가·변경]
    E --> F[법령 근거 부착<br/>korean-law-mcp]
    F --> G[DeviationResult 반환]
    K[(표준조항 코퍼스<br/>SQLite + Chroma)] -.기준.-> D
```

> 모듈별 상세는 각 폴더 README: [contracts](src/contracts/README.md) · [core](src/core/README.md) · [adapter](src/adapter/README.md) · [pipe](src/pipe/README.md)

---

## 기술 스택

| 영역 | 사용 도구 |
| --- | --- |
| 임베딩 / 리랭커 | `dragonkue/BGE-m3-ko` · `dragonkue/bge-reranker-v2-m3-ko` |
| 벡터 검색 | Chroma (dense) + `rank_bm25` + Kiwi 형태소 (sparse) + RRF 융합 |
| 조항 분해(청킹) | LlamaIndex `MarkdownNodeParser` |
| 저장소 | SQLite (조항·관계·독소패턴) |
| 법령 근거 | korean-law-mcp (외부 MCP) |
| 문서 변환 | kordoc (HWP 3.x/5.x, HWPX, HWPML, PDF, XLS, XLSX, DOCX  → 마크다운) |
| 인터페이스 | MCP (`mcp[cli]` / FastMCP) |
| 검증 · 도구 | pydantic · uv · just · pytest |

---

## 프로젝트 구조

```
.
├── data/
│   ├── 01_raw/          # 원본 표준계약서 (HWP)            [커밋]
│   ├── 02_converted/    # 마크다운 변환 (체크포인트)        [커밋]
│   ├── 03_normalized/   # 정규화 조항 JSON = 정답           [커밋]
│   └── migration/       # 스키마 SQL[커밋] + SQLite·Chroma[생성물·미커밋]
├── src/
│   ├── contracts/       # 동결 계약 (enums · models · ports)
│   ├── core/            # 이탈 탐지 순수 함수 (TDD 대상)
│   ├── adapter/         # 외부 I/O (db · vector · embedder · 법령·문서 MCP)
│   ├── pipe/            # 파이프라인 (오프라인 빌드 + 런타임 review)
│   ├── eval/            # 평가 하니스 (metrics · run_eval · ablation)
│   └── config.py
├── tests/               # pytest (TDD 규격서)
├── docs/                # 기획서 + 작업 분배 카드(tasks/)
├── AGENTS.md            # AI·개발자 공용 가이드 (절대 규칙)
└── justfile             # 명령 모음
```

---

### 절대 규칙 (요약)
1. **1차 코드에 LLM 호출 금지** — 검색·매칭·분류만 (해석은 2차).
2. **동결 계약이 단일 진실원** — 스키마·MCP 시그니처 변경은 사전 합의.
3. 사용자 표면 문구는 **"검토 후보"** 프레이밍 ("위법/합법" 단정 금지).
4. **빈 응답 금지** — 매칭 없음은 `NO_MATCH` 등 명시 표식.
5. **평가에 LLM-judge 금지** — 결정론적·재현 가능한 계산만.

---

## 라이선스 / 출처
- 표준계약서: 소프트웨어산업협회(sw.or.kr) · 문화체육관광부(mcst.go.kr)
- korean-law-mcp · kordoc (MIT) / bge 모델 (BAAI) / Chroma (Apache-2.0)
