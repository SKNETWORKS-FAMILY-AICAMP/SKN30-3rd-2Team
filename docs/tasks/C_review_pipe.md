# 팀원 C (+리드) — 검토 조립 (`pipe/review_pipe`)

## 목표
core 의 순수 함수들을 **조립해 계약서 1건 전체를 검토**한다. MCP `review_contract` 의 본체.
사용자 조항마다 [매칭 → 이탈분류 → 누락탐지 → 법령근거] 를 수행해 `DeviationResult[]` 반환.

## 통과할 테스트
- [tests/pipe/test_review_pipe.py](../../tests/pipe/test_review_pipe.py)
  - **fake retriever/grounder 주입** → B의 실제 인덱스 없이도 지금 구현·통과 가능 (TDD)

## 구현 대상
- [src/pipe/review_pipe.py](../../src/pipe/review_pipe.py)
  - `review_contract(clauses, contract_type, *, retriever, grounder, all_standard_clauses, match_threshold=0.5) -> list[DeviationResult]`
  - 조립 재료: `from core import select_best_match, classify_clause_deviation, detect_missing_clauses`

## 반드시 지킬 출력 계약 (동결 — 기획서 4)
1. 반환은 `DeviationResult` 리스트 (4.1 스키마)
2. **검색 결과 없음 → `deviation=NO_MATCH`** (빈 응답 금지, 4.2)
3. 강한 매칭 → `matched_standard` 채우고 `grounding` 부착
4. 어느 사용자 조항에도 안 잡힌 표준조항 → `MISSING` 으로 포함 (3.2)
> ⚠ `review_contract` 시그니처는 MCP 계약과 직결 — 바꾸려면 리드와 합의.

## 완료 조건 (DoD)
- [x] `tests/pipe/test_review_pipe.py` 전부 통과
- [ ] (통합) B의 인덱스 빌드 후 실제 `adapter.vector`·`adapter.koreanLaw` 주입으로 동작 확인
- [x] LLM·해석 문장 생성 없음 (검색·비교·분류만 — AGENTS.md 규칙 #1)

## 참고
- [src/core/README.md](../../src/core/README.md), [src/pipe/README.md](../../src/pipe/README.md)
- 리랭커(`adapter.reranker`) 연결로 매칭 정밀화 (고도화: 검색 후보 재정렬)
