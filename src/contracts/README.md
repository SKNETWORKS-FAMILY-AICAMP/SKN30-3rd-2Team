# src/contracts/ — 계약(인터페이스) + 구현체

팀 전체가 같은 데이터 모양·함수 시그니처를 보고 **병렬로** 일하기 위한 공통 기준입니다.
크게 두 층으로 나뉩니다.

| 층 | 위치 | 성격 |
| --- | --- | --- |
| **동결 계약** | `enums.py` · `models.py` · `ports.py` | ⚠ **frozen.** 외부 의존 0의 순수 약속 |
| **포트 구현체** | `implement/` (+ 일부는 `adapter/`) | 약속을 실제로 만족시키는 코드 (어댑터 조합) |

> ⚠ **동결 영역(enums·models·ports)** 은 기획서 3·4장에 해당합니다. **변경하려면 코드 수정 전에 PM/리드에게 먼저 물어보세요.** (AGENTS.md 규칙 #2)
> `implement/` 는 동결이 아닙니다 — 자유롭게 발전시키되 **포트 시그니처는 지켜야** 합니다.

---

## 1. 동결 계약

| 파일 | 내용 |
| --- | --- |
| `enums.py` | 닫힌 값 집합. `ContractType` / `Category` / `Deviation` / `ToxicPattern` / `EdgeRelation`. **여기 없는 값은 어디에도 쓰지 않습니다.** |
| `models.py` | pydantic 데이터 모델. `Clause` · `StandardClause` · `ClauseRelation` · `ToxicPatternRecord` · `GroundingLaw` · `DeviationResult` |
| `ports.py` | `Protocol` 인터페이스. `Parser` / `Embedder` / `Retriever` / `Grounder` / `Graph` |

### 왜 Protocol(포트)인가
코어 로직이 **"무엇을 하는지"(인터페이스)만 알고 "어떻게 하는지"(구현)는 모르게** 분리합니다(의존성 역전).
- 코어는 `Retriever`라는 **약속**에만 의존 → 실제 검색이 Chroma든 뭐든 코어를 안 고침
- 테스트에서 가짜(fake) 구현을 끼우기 쉬움 → **TDD 가능** (예: `review_pipe` 테스트의 FakeRetriever)
- 구현체를 교체/추가해도 코어가 안 깨짐

---

## 2. 포트 구현체 (Implementations)

각 포트는 어딘가에 **구현체**가 있어야 실제로 동작합니다. 구현체는 두 곳에 둡니다.

### 어디에 두나 — 두 가지 규칙
- **`adapter/` 기본구현:** 단일 도구가 포트 시그니처와 **그대로 일치**하면, 그 어댑터 클래스 자체가 구현체.
- **`contracts/implement/` 조합 구현:** **여러 어댑터 + 변환 로직**을 엮어야 포트를 만족시키는 경우. (`from adapter import ...` 로 도구를 가져와 조합)

### 포트 ↔ 구현체 ↔ 상태
| 포트 | 구현체 | 위치 | 사용 도구 | 상태 |
| --- | --- | --- | --- | --- |
| `Parser` | `KordocParser` | `implement/kordoc_parser.py` | `kordoc` + `splitter` + 제N조 파싱 | ✅ |
| `Grounder` | `KoreanLawGrounder` | `implement/korean_law_grounder.py` | `koreanLaw` + `CATEGORY_QUERIES` 매핑 + 텍스트 파싱 | ✅ |
| `Retriever` | `VectorManager` (`vector`) | `adapter/vector_manager.py` | Chroma + BM25 + RRF | ✅ 기본구현 |
| `Embedder` | `Bgem3Embedder` (`embedder`) | `adapter/embedding_model.py` | bge-m3 | ✅ 기본구현 |
| `Graph` | `ClauseGraph` *(예정)* | `implement/clause_graph.py` | `db`(clause_relations) + `core.traverse_related_risks` | 🔴 미구현 — 고도화 A([F_graph](../../docs/tasks/F_graph.md)) |

> 새 구현체를 만들 때: **단일 어댑터로 끝나면 `adapter/`**, **조합·변환이 필요하면 `implement/`**. 둘 다 반드시 `ports.py` 의 시그니처를 구현(`class X(Grounder)`)할 것.

### 사용 예 (구현체 직접 사용)
```python
from contracts.enums import Category
from contracts.implement import KordocParser, KoreanLawGrounder

clauses = KordocParser().parse("계약서.hwp")            # -> List[Clause]
laws = KoreanLawGrounder().get_grounding(Category.IP_OWNERSHIP)  # -> List[GroundingLaw]

# 기본구현(Retriever·Embedder)은 어댑터 싱글톤으로
from adapter import vector, embedder
hits = vector.search("standard_clauses", "저작권 귀속", top_k=5)
```

> 런타임 조립(`pipe/review_pipe.py`)은 이 구현체들을 **주입**받아 씁니다 — 그래서 테스트에선 fake로, 실제론 위 구현체로 바꿔 끼울 수 있습니다.

---

## 규칙
- enum에 없는 문자열을 코드에 직접 쓰지 말 것 (`"MISSING"` ❌ → `Deviation.MISSING` ✅).
- 빈 응답 금지: 매칭/조회 실패는 빈 리스트나 `Deviation.NO_MATCH` 등 **명시 표식**으로. (기획서 4.2)
- **동결 계약(enums·models·ports) 변경은 사전 합의.** `implement/` 추가·수정은 자유(단 포트 시그니처 준수).
