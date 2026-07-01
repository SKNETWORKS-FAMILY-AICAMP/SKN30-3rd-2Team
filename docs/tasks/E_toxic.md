# 고도화 B — 독소조항 양방향 검색 (`toxic`)

> 기획서 7.2 · 업무 #18 · **코어(A·B·C)가 도는 것을 확인한 뒤 착수**

## 목표
"표준엔 없지만 사용자에게 **해로운 추가 조항**"을 잡는다. 기존이 *표준→사용자*(빠짐/다름) 방향이라면,
여기에 **독소 패턴→사용자** 방향 검색 축을 하나 더 더한다. LLM 없이 검색·매칭으로 동작.

## 통과할 테스트
- [tests/core/test_toxic.py](../../tests/core/test_toxic.py) — `detect_toxic_patterns` 순수 로직 (**이미 통과**)
- 추가 작성(TDD): 독소 컬렉션 빌드/검색 통합 테스트 (담당자가 작성)

## 구현 대상
1. **독소 인덱스 빌드** — `toxic_patterns` 테이블을 Chroma `toxic_patterns` 컬렉션으로 임베딩 적재.
   - `pipe/build_index.py` 에 `build_toxic_index()` 추가(표준조항 빌드와 동일 패턴) → `just build-db` 에 연결.
2. **양방향 검색 배선** — 사용자 조항을 독소 컬렉션에 검색 → `(ToxicPattern, score)` → `core.detect_toxic_patterns(threshold)` → 결과를 `DeviationResult.toxic_patterns` 에 채움.
   - 위치: `pipe/review_pipe.py` 의 review 흐름 안(또는 보조 함수).

## 입력 / 출력 계약
- 입력: 사용자 조항 텍스트 + `toxic_patterns` 컬렉션
- 출력: `DeviationResult.toxic_patterns: list[ToxicPattern]` (이미 모델에 존재)
- 데이터: [data/03_normalized/toxic_patterns.json](../../data/03_normalized/toxic_patterns.json) (`ToxicPatternRecord` 규격)

## 완료 조건 (DoD)
- [x] `toxic_patterns` Chroma 컬렉션이 `just build-db` 로 함께 빌드됨
- [ ] 독소 조항(예: 저작권 전부 무상귀속)이 매칭되어 `toxic_patterns` 에 표식됨
- [ ] 골든셋 `gold_toxic` 라벨로 검증 (eval 연계)
- [ ] LLM 없이 검색·매칭만 (AGENTS.md 규칙 #1)

## 참고
- [src/core/README.md](../../src/core/README.md) (`detect_toxic_patterns`), `enums.ToxicPattern`
- [src/pipe/README.md](../../src/pipe/README.md) §고도화 설계
- 평가: [eval/README.md](../../eval/README.md) 의 `gold_toxic`
