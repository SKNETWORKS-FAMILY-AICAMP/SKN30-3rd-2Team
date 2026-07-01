# [고도화 H] 서브청크 커버리지 체크 — 항(項) 단위 삭제 탐지

> 기획서 7 · **[G_sub_chunk](G_sub_chunk.md) 3단계의 상세 구현 계획** · roll-up(1·2단계)이 배선된 것을 확인한 뒤 착수

## 목표
매칭된 부모 조항 **안에서 "표준의 어느 항이 사용자 계약서에 빠졌나"** 를 탐지한다.
현재 누락 탐지(`detect_missing_clauses`)는 **조(條) 단위**("표준 제20조가 통째로 없음")만 잡는다.
커버리지 체크는 이를 **항(項) 단위**로 내려, 거대 조항의 **임베딩 희석**(9/10 항 일치 시 `NONE` 오탐)을 잡는다.
→ 미커버 항이 있으면 해당 조항을 **`Deviation.CHANGED` 로 상향**해 2차(LLM)에 전달한다. (1차는 탐지만, 해석 금지)

## 현재 상태 (정정)
- `core.roll_up_sub_chunks` — 배선 완료(부모 recall 보강). ✅
- `core.check_coverage` ([matching.py](../../src/core/matching.py)) — **순수함수 존재·export 만 됨. 미배선·무테스트.**
  - ⚠ [G_sub_chunk](G_sub_chunk.md) §4 DoD 의 "커버리지 체크 구현·단위테스트 통과 `[x]`" 는 실제와 불일치 — 본 문서가 그 미완분을 담당.

## 왜 "한 줄 배선"이 아닌가 — 호출 전제가 통째로 빠져 있음
`check_coverage(standard_ids, similarity_matrix, threshold)` 는 순수 계산만 한다. 이 앞뒤로 4가지가 필요하다.

```
[표준 항 M개]  ──┐
                 ├─→  M×N 유사도 매트릭스  ──→  core.check_coverage  ──→  미커버 표준 항 id
[사용자 항 N개] ─┘                                    ↓
                                        (미커버 존재 → 매칭 조항을 CHANGED 로 상향)
```

- **M축(표준 항)**: 있음. `standard_sub_chunks` (오프라인 구축).
- **N축(사용자 항)**: **없음.** 파서(kordoc)는 사용자 계약서를 **조 단위 `Clause`** 로만 분해 — 항 단위로 안 쪼갠다.
- **M×N 매트릭스**: 표준 항 i × 사용자 항 j 유사도 계산기 필요.
- **보고**: 미커버 → `CHANGED` 상향 (새 모델 필드 불필요).

## 구현 대상

1. **사용자 조항 → 항 분할 (런타임, 신규)**
   - 매칭된 사용자 `Clause.text` 를 항/호 단위 N개로 분할. **G 1단계의 분할 조건과 동일 규칙**(500자 초과 OR 항·호 기호 3개 이상)을 재사용.
   - ⚠ 오프라인(`build_index`)과 런타임이 **같은 분할 로직**을 쓰도록 공용 함수로 추출(중복 구현 금지). 후보: [adapter/markdown_splitter.py](../../src/adapter/markdown_splitter.py) 확장 또는 신규 순수 유틸.
   - 조건 미달(단순 조항)은 커버리지 체크 대상 아님 → 스킵.

2. **매칭 부모의 표준 항 로드**
   - `SELECT * FROM standard_sub_chunks WHERE parent_clause_id = ?` ([Database](../../src/adapter/port.py) 포트).
   - G §0단계 설계대로 **SQLite 에서 열거**(Chroma WHERE 는 전체 열거에 부적합). 부모별 서브청크 맵을 `review_contract` 에 주입하는 방식도 가능(= `all_standard_clauses` 패턴).

3. **M×N 유사도 매트릭스 계산**
   - 각 표준 항 i 에 대해 사용자 항 N개와의 유사도 행을 만들어 M×N 구성.
   - **(권장) 이미 주입된 `Reranker.compute_scores(std_i, [user_subs])` 재사용** → 로짓 → `core.sigmoid` → 임계 비교. 새 포트 주입 불필요, 크로스인코더라 정밀도↑. (비용: 조당 M×N 쌍)
   - (대안) `Embedder.compute_similarity` (cosine, 저비용) — 단 embedder 를 `review_contract` 에 **추가 주입**해야 함(동결 시그니처 변경 → §2 사인오프).

4. **커버리지 판정 + 상향 (조립)**
   - `core.check_coverage(standard_ids, matrix, coverage_threshold)` → 미커버 id 목록.
   - 대상: **매칭된(`NONE`/`CHANGED`) + 복합 부모(서브청크 2개 이상)** 조항만.
   - 미커버 존재 & 현재 `NONE` → **`CHANGED` 로 상향** + grounding 부착. 이미 `CHANGED` 면 유지.
   - 위치: 순수 판정은 `core.check_coverage`, 조립(분할·로드·매트릭스·상향)은 [review_pipe.py](../../src/pipe/review_pipe.py) (또는 신규 `core/coverage.py` 는 순수부만).

## 입력 / 출력 계약
- 입력: 매칭된 `Clause.text` + 부모의 `standard_sub_chunks` + 유사도 계산 포트(Reranker 재사용 권장).
- 출력: **새 모델 필드 없음.** 미커버 → `DeviationResult.deviation = CHANGED` 상향(+grounding). 동결 `DeviationResult`·MCP 시그니처 무변경.
- 신규 파라미터: `coverage_threshold: float`(유사도 스케일, `match/change_threshold` 와 별개 — eval 로 캘리브레이션). `use_coverage: bool = True`(ablation).

## 미결정 / 사인오프 필요 (AGENTS.md §2)
- **유사도 계산기**: Reranker 재사용(주입 무변경) vs Embedder 주입(시그니처 변경). → **채택: Reranker 재사용** ✅
- **표준 항 공급**: 런타임 DB 조회 vs 사전 주입 맵. → **채택: `all_standard_sub_chunks` 사전 주입 맵** ✅
- **미커버 서브청크 ID 노출 여부**: `DeviationResult.uncovered_sub_chunk_ids: List[str]` 필드 추가로 확정 ✅. NONE→CHANGED 상향 시에만 채워지며(표준 측 항 id), 나머지 조항은 항상 `[]`. 2차 LLM은 `deviation==CHANGED`일 때만 이 필드를 읽어 검토 범위를 좁힘.

## 완료 조건 (DoD)
- [ ] 사용자 조항 런타임 항 분할기 구현 (오프라인과 공용 로직)
- [ ] 매칭 부모의 표준 서브청크 로드 경로 (SQLite `WHERE parent_clause_id`)
- [ ] M×N 유사도 매트릭스 + `core.check_coverage` 배선
- [ ] 미커버 항 존재 시 매칭 조항 `NONE→CHANGED` 상향 + grounding
- [ ] `tests/core/` 에 `check_coverage` 순수 단위테스트, `tests/pipe/` 에 fake 계산기로 통합테스트
- [ ] `coverage_threshold` eval 캘리브레이션 (cosine/sigmoid 스케일)
- [ ] Ablation: 거대 조항 "항 삭제" 골든셋에서 **Coverage Recall** 개선 증명 (G §3)
- [ ] LLM 없이 검색·비교만 (규칙 #1) / 결정론적 지표 (규칙 #5)

## 참고
- 부모 설계: [G_sub_chunk](G_sub_chunk.md) (0~4단계, 특히 3단계·4단계)
- 순수함수: [src/core/README.md](../../src/core/README.md) (`check_coverage`, `sigmoid`)
- 포트: [adapter/port.py](../../src/adapter/port.py) (`Reranker.compute_scores`, `Embedder.compute_similarity`, `Database`)
- 파이프: [src/pipe/README.md](../../src/pipe/README.md) §고도화 설계 · [review_pipe.py](../../src/pipe/review_pipe.py)
- 평가: [eval/README.md](../../eval/README.md) (Coverage Recall) · [ablation.py](../../eval/ablation.py)
