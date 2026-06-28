# 팀원 A — 표준조항 정규화 (`pipe/normalize`)

## 목표
변환된 마크다운(`data/02_converted/*.md`)을 **조항 단위로 분해하고 category 라벨을 붙여**
`data/03_normalized/*.json`(정답 데이터)을 만든다. 이게 전체 시스템의 **기준(정답)** 이다.

## 통과할 테스트
- [tests/pipe/test_normalize.py](../../tests/pipe/test_normalize.py)

## 구현 대상
- [src/pipe/normalize.py](../../src/pipe/normalize.py)
  - `split_markdown_clauses(md_text) -> list[Clause]` — `adapter.splitter` 로 청크를 나눈 뒤 `제N조` 헤더만 골라 `Clause` 로. (순수 분해는 splitter 가 이미 해줌 — 재구현 금지)
  - `label_category(num, title, text) -> Category` — 키워드 규칙으로 category 부여
  - `normalize_file(md_path, contract_type, version) -> list[StandardClause]` — 위 둘 조립 + `clause_id`·`source` 부여
- [src/pipe/2.normalize.py](../../src/pipe/2.normalize.py) — CLI: 02_converted 순회 → 03_normalized JSON 저장

## 입력 / 출력 계약
- 입력: `### 제N조(제목)` 헤더가 있는 마크다운
- 출력: `StandardClause` 규격 JSON ([data/README.md](../../data/README.md) 참고). enum 값은 `src/contracts/enums.py` 와 일치해야 적재됨.

## 완료 조건 (DoD)
- [ ] `tests/pipe/test_normalize.py` 전부 통과 (skip 제거 후)
- [ ] `data/03_normalized/standard_clauses.sw_freelance.json` 에 SW 도급계약서 전체 조항 정규화
- [ ] `just migrate` 가 새 데이터로 에러 없이 적재됨
- [ ] (가능하면) 문화예술용역 계약서도 동일 절차로 추가

## 참고
- [src/pipe/README.md](../../src/pipe/README.md), [src/adapter/README.md](../../src/adapter/README.md) (splitter 사용법)
- category 후보: `enums.py` 의 `Category` (PAYMENT/IP_OWNERSHIP/...)
