# src/server/ — MCP 서버

헥사고날 아키텍처의 **최외곽 표면**. `pipe/review_pipe`가 조립한 결과를 외부(AI 클라이언트·2차 웹앱)에 MCP 도구로 노출합니다.

- `server.py` — FastMCP 앱 초기화 + 도구 등록
- `app.py` (예정) — 실행 진입점 (`uv run python src/server/app.py`)

> 작업 전 [AGENTS.md](../../AGENTS.md) · [기획서 4장](../../docs/01.mvp_기획.md) · [pipe/README.md](../pipe/README.md) 를 읽으세요.
> **MCP 시그니처(도구 이름·입출력)는 동결 계약입니다 — 변경 시 PM/리드와 먼저 합의하세요.**

---

## 1. 노출 도구 (기획서 4장 동결)

| 도구 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `parse_contract` | 계약서 파일 → 조항 목록 | `file_path`, `contract_type` | `List[Clause]` |
| `match_clause` | 단일 조항 → 표준조항 후보 검색 | `clause_text`, `contract_type` | `List[{clause_id, score, standard_text}]` |
| `review_contract` | 전체 검토(파싱→매칭→이탈→근거) | `file_path`, `contract_type` | `List[DeviationResult]` |
| `get_grounding` | 카테고리 → 관련 법령 조문 | `category` | `List[GroundingLaw]` |

모든 도구는 **stateless** — 한 번의 호출이 그 자체로 완결, 서버가 이전 상태를 기억하지 않음.

### 1.1 확장 도구 (동결 4장 밖 — 자유 추가, MCP 조합력 강화용)

동결 4장 표 자체는 바꾸지 않고, 별도 도구로 추가한 것들. 기존 4개 도구의 시그니처는 그대로다.

| 도구 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `classify_clause` | 단일 조항 → 이탈 판정(재정렬+매칭+분류까지 완결) | `clause_text`, `contract_type` | `{deviation, confidence, matched_standard, grounding}` |
| `list_contract_types` | 지원 계약 종류 조회 (Discovery) | 없음 | `[str]` |
| `list_categories` | 카테고리 + 설명 + 앵커 키워드 조회 (Discovery) | 없음 | `[{value, description, anchors}]` |
| `list_toxic_patterns` | 독소 패턴 종류 조회 (Discovery) | 없음 | `[str]` |

- `match_clause`(검색 후보만 나열)와 `classify_clause`(최종 이탈 판정까지 완결)는 역할이 다르다.
  프론트가 "이 조항 하나만 빠르게 이탈 판정"하려면 `parse_contract` → `classify_clause` 체이닝을 쓰면
  된다 (전체 `review_contract` 없이도 부분 워크플로우가 성립).
- Discovery 도구는 `contract_type`/`category`/`toxic_pattern` enum 값을 **하드코딩하지 않고 런타임에
  조회**하게 하기 위함. 도구 docstring에도 값 목록을 박아넣지 말고 이 도구들을 참조하도록 안내할 것.

### 1.2 Resource (읽기 전용 표준조항 브라우징)

| Resource URI | 목적 |
|---|---|
| `standard://{contract_type}` | 해당 계약 유형의 표준조항 요약 목록(`clause_id`, `title`, `category`) |
| `standard://{contract_type}/{clause_id}` | 표준조항 원문 전체 |

Tool이 아닌 Resource로 노출한 이유: "SW 프리랜서 표준계약서 12조 원문 보여줘" 같은 요청은 액션(도구
호출)이 아니라 데이터 열람이므로, MCP 클라이언트가 도구를 고르지 않고도 바로 읽을 수 있게 한다.

---

## 2. 구현 구조

```python
# server.py
from fastmcp import FastMCP
mcp = FastMCP("WorkShield")

# 도구는 각 함수에 @mcp.tool() 데코레이터로 등록
# 의존성(parser·retriever·grounder·db)은 싱글턴으로 주입
```

```
server.py
  ├── _load_standards(contract_type)  — DB에서 표준조항 로드 (공통 헬퍼)
  ├── @mcp.tool() parse_contract(...)
  ├── @mcp.tool() match_clause(...)
  ├── @mcp.tool() review_contract(...)   ← 핵심, 아래 예외처리 참고
  └── @mcp.tool() get_grounding(...)
```

---

## 3. 비즈니스 예외 처리 설계

### 3.1 원칙: infra 예외 vs 비즈니스 예외 분리

```
infra 예외   (파일 없음·DB 연결 실패 등)  → raise → FastMCP가 error 응답으로 변환
비즈니스 예외 (명제 불성립·규칙 위반 등)  → server에서 catch → 구조화된 경고 메시지 반환
```

MCP는 JSON 소비자이므로 비즈니스 예외를 throw로 처리하면 2차 LLM이 오해 없이 읽기 어렵습니다.
`review_contract` 내부는 도메인 예외를 raise하고, **server 레이어가 catch해서 응답을 구성**합니다 (Option A).

### 3.2 예외별 처리 위치 및 방법

| # | 상황 | 발생 위치 | server 처리 |
|---|---|---|---|
| 1 | 파싱 결과 0건 | `KordocParser.parse()` → `[]` 반환 | `EmptyDocumentError` raise → 빈 리스트 + 경고 메시지 반환 |
| 2 | 해당 `contract_type` 표준 코퍼스 없음 | `_load_standards()` → `[]` 반환 | `CorpusUnavailableError` raise → 경고 메시지 반환 |
| 3 | Retriever `contract_type` 필터 누락 | `vector.search()` 결과 오염 | `metadata_filter` 필수 인자화 — 타입 레벨에서 방지 |
| 4 | 조항 결과 소실 (NO_MATCH 누락) | `review_pipe` 내부 | `PipelineIntegrityError` raise → server에서 catch 후 500 수준 에러 로깅 |
| 5 | `match_threshold > change_threshold` | `review_contract` 진입 시 | `InvalidConfigError` raise → 설정 오류 메시지 반환 |
| 6 | `clause_id` 중복 | SQLite 적재 시점 | `UNIQUE` 제약으로 적재 실패 — 런타임 도달 불가 |
| 7 | 조항 본문 실질적 빈 값 | `review_pipe` 내부 | 해당 `DeviationResult`의 `confidence=0.0` + 경고 문자열 |
| 8 | `deviation=NONE` + `toxic_patterns` 공존 | `review_pipe` 내부 | 정상 응답 — 두 축은 직교. 경고 없이 둘 다 보고 |

### 3.3 `review_contract` 도구 예외 처리 흐름

```python
@mcp.tool()
def review_contract(file_path: str, contract_type: str) -> dict:
    try:
        ct = ContractType(contract_type)      # 잘못된 enum 값 → ValueError → FastMCP error
    except ValueError:
        return {"error": f"지원하지 않는 계약 종류: {contract_type}"}

    try:
        clauses = parser.parse(file_path)     # FileNotFoundError·RuntimeError → infra
    except FileNotFoundError as e:
        return {"error": str(e)}

    if not clauses:                           # 1번: 빈 문서
        return {
            "status": "EMPTY_DOCUMENT",
            "message": "조항 추출 0건 — 스캔 PDF이거나 파싱 실패 가능성",
            "results": []
        }

    standards = _load_standards(ct)
    if not standards:                         # 2번: 코퍼스 없음
        return {
            "status": "CORPUS_UNAVAILABLE",
            "message": f"{contract_type} 표준 코퍼스 없음 — 비교 불가",
            "results": []
        }

    try:
        results = review_contract_pipe(       # 5번 InvalidConfig, 4번 PipelineIntegrity
            clauses=clauses,
            contract_type=ct,
            retriever=vector,
            grounder=koreanLaw,
            all_standard_clauses=standards,
        )
    except InvalidConfigError as e:           # 5번: 임계값 설정 모순
        return {"status": "INVALID_CONFIG", "message": str(e), "results": []}
    except PipelineIntegrityError as e:       # 4번: 조항 소실 — 심각한 버그
        logging.error(f"[CRITICAL] 파이프라인 무결성 오류: {e}")
        return {"status": "PIPELINE_ERROR", "message": "내부 오류 — 관리자에게 문의", "results": []}

    return {"status": "OK", "results": [r.model_dump() for r in results]}
```

> `status` 필드를 포함한 응답 래퍼 구조는 **server 레이어 전용**입니다.
> `contracts/` 동결 스키마를 건드리지 않고 `server/` 안에서만 정의·사용합니다.

---

## 4. 도메인 예외 클래스 위치

`src/pipe/exceptions.py` 에서 정의하고 server에서 import합니다.

```python
# src/pipe/exceptions.py
class EmptyDocumentError(ValueError): ...       # 1번: 파싱 0건
class CorpusUnavailableError(ValueError): ...   # 2번: 표준 코퍼스 없음
class InvalidConfigError(ValueError): ...       # 5번: 임계값 설정 모순
class PipelineIntegrityError(RuntimeError): ... # 4번: 조항 소실
```

`review_pipe.py` 에서 raise하고, `server.py` 에서 catch합니다.
`core/` 는 이 예외를 알 필요 없습니다 — pipe 레이어에서만 사용.

---

## 5. 실행

```bash
# 개발 실행
uv run python src/server/app.py

# MCP 클라이언트에서 연결
# stdio 방식: command = "uv run python src/server/app.py"
```

---

## 6. 구현 순서 (의존성 기준)

```
1. pipe/review_pipe.py 완성 (담당: 팀원 C)  ← 선행 블로커
2. 도메인 예외 클래스 정의
3. server.py — parse_contract, get_grounding 먼저 (의존성 낮음)
4. server.py — review_contract (review_pipe 완성 후)
5. server.py — match_clause
6. 통합 테스트 — MCP 클라이언트로 실제 호출 검증
```

## 7. 절대 규칙 재확인

- **LLM 호출 없음**: 서버 레이어에서도 생성 AI 호출 금지. 결과 해석·판단 문장 생성 금지.
- **빈 응답 금지**: 모든 도구는 실패 시에도 `status` + `message` 를 포함한 구조화된 응답 반환.
- **단정 표현 금지**: "위법", "소송에서 이긴다" 같은 표현을 응답에 포함하지 않음.
