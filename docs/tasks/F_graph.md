# 고도화 A — 계약-조항 의존성 그래프 (`graph`)

> 기획서 7.1 · 업무 #17 · **코어(C 검토 흐름)가 도는 것을 확인한 뒤 착수**

## 목표
계약서는 조항이 서로 얽힌 시스템이다. 한 조항이 표준에서 벗어나면 연결된 조항도 함께 위험해진다.
**"이 조항이 이탈하면 함께 검토해야 할 조항"** 을 연결을 따라 찾아 `related_risk_clauses` 로 제시한다.
→ 사용자 조항 → 표준 조항 → (법령) 으로 이어지는 **설명 가능한 경로**(provenance).

## 통과할 테스트
- [tests/core/test_graph.py](../../tests/core/test_graph.py) — `traverse_related_risks` 순수 DFS (**이미 통과**)
- 추가 작성(TDD): `clause_graph` 어댑터 통합 테스트 (DB 의존 → 통합)

## 구현 대상
1. **Graph 포트 구현체** — 신규 `src/contracts/implement/clause_graph.py` (`ClauseGraph(Graph)`, [ports.Graph](../../src/contracts/ports.py) 구현). DB·core·변환을 엮는 **조합 구현**이라 `implement/` 에 둡니다.
   - `add_relation(source_category, target_category, relation_type)` : `clause_relations` 에 INSERT.
   - `get_related_risks(clause_id) -> list[str]` :
     ① `clause_id` → `category` 조회(`standard_clauses`)
     ② `clause_relations` 로 **category 인접목록** 구성
     ③ `core.traverse_related_risks` 로 연관 category 탐색 (중복 구현 금지)
     ④ 연관 category → **clause_id 로 역매핑**해 반환
2. **review_contract 결합** — 이탈(`CHANGED`/`MISSING` 등) 조항의 `related_risk_clauses` 를 채움.
3. **(stretch) `impact_map` 조합** — korean-law-mcp 의 조문↔판례 연결로 법령→판례 경로 확장. *단 현재 `koreanLaw` 어댑터에 해당 기능이 없으니 지원 여부 확인 후, 없으면 2차로 미룸.*

## 입력 / 출력 계약
- 핵심: 엣지는 **category 레벨**, 입출력은 **clause_id 레벨** → 어댑터가 둘을 변환하는 다리.
- 출력: `DeviationResult.related_risk_clauses: list[str]` (clause_id, 이미 모델에 존재)
- 데이터: [data/03_normalized/clause_relations.json](../../data/03_normalized/clause_relations.json) (`ClauseRelation` 규격)

## 완료 조건 (DoD)
- [ ] `adapter/clause_graph.py` 가 `clause_relations` 로 인접목록을 만들고 `core.traverse_related_risks` 재사용
- [ ] `get_related_risks("sw_freelance-art20")` 이 연관 조항 clause_id 를 반환
- [ ] review_contract 결과에 `related_risk_clauses` 채워짐
- [ ] 별도 그래프 DB 없이 SQLite + 파이썬 탐색 (기획서 7.1)

## 참고
- [src/core/README.md](../../src/core/README.md) (`traverse_related_risks`), `enums.EdgeRelation`
- [src/pipe/README.md](../../src/pipe/README.md) §고도화 설계
