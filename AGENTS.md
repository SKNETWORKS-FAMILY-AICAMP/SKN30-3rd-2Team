# AGENTS.md — WorkShield

## 한 줄
사용자 프리랜서 용역계약서를 표준계약서와 **조항 단위로 비교**해 이탈(누락/추가/변경)을
탐지하는 RAG MCP 시스템. **1차는 LLM 없이** 검색·비교·규칙만. (기획서: [docs/01.mvp_기획.md](docs/01.mvp_기획.md))

## ⛔ 절대 규칙 (위반 시 명제가 무너짐)
1. **1차 코드에 LLM 호출 금지.** 조항 "해석"·"불리함 판단"을 생성하지 말 것.
   검색·매칭·분류만. (해석은 2차) (데모는 허용)
2. **동결 계약이 단일 진실원.** 조항 스키마(기획서 3장)·MCP 시그니처(4장)를
   임의 변경 금지. 변경이 필요하면 코드 수정 전에 사람에게 먼저 물을 것.
3. **사용자 표면 문구는 "검토 후보" 프레이밍.** "위법/합법", "소송에서 이긴다"
   같은 단정 생성 금지.
4. **빈 응답 금지.** 매칭 없음은 `deviation:"NO_MATCH"` 등 명시 표식으로 반환.
5. **평가에 LLM-judge 금지.** 지표는 결정론적·재현 가능한 계산만.

## 아키텍처 (헥사고날: 코어는 외부를 모른다)
```
contracts(동결 계약)  ← 모두가 의존하는 약속: enums · models · ports(Protocol)
   ▲              ▲
core(순수함수)     adapter(외부 I/O)   ← ports 구현: db·vector·embedder·reranker·kordoc·koreanLaw
   ▲              ▲
   └──── pipe(조립) ────┘            ← 오프라인 준비 + 런타임 review_contract
                  ▲
            mcp_server / demo         ← FastMCP 노출 + 데모
```
- **core**는 adapter를 직접 import하지 않음. 외부 작업은 **인자로 주입**. → 순수 → 테스트 용이.
- 각 폴더에 `README.md` 있음 — 작업 전 해당 폴더 README를 읽을 것.

## 폴더 지도
| 경로 | 역할 |
| --- | --- |
| `src/contracts/` | 동결 스키마·포트 (단일 진실원) |
| `src/core/` | 이탈 탐지 알고리즘 (순수 함수, TDD 대상) |
| `src/adapter/` | DB·모델·외부 MCP 어댑터 (싱글톤) |
| `src/pipe/` | 데이터 준비(1→2→3) + 런타임 검토 파이프 |
| `data/` | `01_raw`→`02_converted`→`03_normalized`(정답)→`migration`(생성물) |
| `tests/`, `eval/` | pytest 테스트 / 평가 하니스 |

## 명령
```bash
just setup        # 최초 1회: node·MCP·uv·모델 다운로드
just build-db     # 03_normalized JSON → SQLite → Chroma 인덱스 재생성
just migrate      # SQLite 까지만
uv run pytest     # 테스트
```

## 형상관리 (정답은 git, 인덱스는 재생성)
- git 관리: `data/03_normalized/*.json`(정답) · `data/migration/*.sql`(스키마) · `02_converted/*.md`.
- git 제외(재생성물): `*.sqlite3` · Chroma 인덱스. → 바이너리 주고받지 않음. 자세히는 [data/README.md](data/README.md).

## 컨벤션
- 패키지 import는 `src/` 루트 기준: `from contracts...`, `from adapter import db`, `from core import ...`.
- enum 값을 문자열로 직접 쓰지 말 것 (`Deviation.MISSING` ✅ / `"MISSING"` ❌).
- 주석·docstring은 한국어. 타입힌트 + pydantic 모델 사용.
- 외부/코어 모두 **조용한 실패 금지** — 빈 값 대신 명시 표식·예외.

## 테스트 (TDD)
- 모듈 규격은 `tests/`의 테스트로 고정됨. **테스트를 먼저 읽고**, 그것을 통과하도록 구현.
- `core/`는 순수 함수라 테스트가 곧 명세. 새 로직은 테스트부터.
