# 팀원 D — 평가 하니스 (`src/eval/`) + 골든셋

> 기획서 8장 · 결정 로그 [07-01 §12~](../dicision/07-01.md) · 필독 [src/eval/README.md](../../src/eval/README.md)
> ⚠ `eval/` 패키지는 `src/eval/` 로 이동됨(setuptools packages·pytest pythonpath 동기화 완료). 아래 경로는 전부 새 위치 기준.

## 목표
LLM 없이 **검색·이탈 탐지·독소 탐지 품질을 수치로 측정**한다. 특히 ablation(8.5)은 "RAG가
필요한가"를 주장이 아니라 **수치로 증명하는 대표 결과물**이므로 필수.

---

## 현재 상태 (2026-07-01)

| 구성 | 상태 |
| --- | --- |
| 순수 집계 `metrics.py`·`run_eval.evaluate`·`ablation.run_ablation` | ✅ 완성 · 테스트 통과(10 passed) |
| 골든셋(합성) 3종 92건 | ✅ 작성 완료 (아래 분포) · 독소 라벨 enum 정합성 정리 완료 |
| **Driver**(골든셋 → 실제 검색 → cases, 4변형) | ✅ 구현 완료 — [src/eval/run_eval.py](../../src/eval/run_eval.py) `build_cases`/`build_cases_by_variant` |
| 이탈 분류 P/R 하니스 (A-2) | ✅ 구현 완료 — `review_golden_clauses` + `deviation_precision_recall` |
| 독소 P/R 하니스 (A-3) | ✅ 구현 완료 — `toxic_precision_recall` (같은 review 결과 재사용) |
| 통합 실행 리포트(`main()`) | ✅ 구현 완료 · ⏳ **실제 수치는 미측정**(담당자가 `just build-db` 후 실행 예정) |
| 트랙 B(MISSING Recall·강건성) | 📋 **설계·실행계획 확정** (아래 §트랙 B) · 실제 문서 미확보 |

**골든셋 분포(92건):** deviation = NONE 43 / CHANGED 43 / EXTRA 6 / **MISSING 0**,
trap = none 34 / paraphrase 32 / contradiction 19 / partial 7 / **reorder 0**,
독소 라벨 26건(전부 `ToxicPattern` enum 정합).

> MISSING·reorder 가 0인 건 버그가 아니라 **구조**다 — 합성셋은 조항 단위(독립 질의)라
> MISSING(계약 전체에 표준조항이 없음)을 담을 수 없다. → **트랙 B**(계약 단위) 소관.

---

## 평가 구조 — 두 트랙 (실제 vs 합성)

```
                 ┌─ 트랙 A: 합성 골든셋 (조항=독립 질의)  → 검색품질·분류·독소·ablation
golden ─ driver ─┤
                 └─ 트랙 B: 실제 계약서 (문서=계약 단위)   → MISSING Recall·강건성 스팟체크
                          ↓ 공유
                 metrics.py (완성) ← evaluate() / run_ablation() / precision_recall()
```

두 트랙은 **같은 `metrics.py`로 수렴**한다. driver 만 트랙별로 cases 를 만든다.

### 트랙 A — 합성 골든셋
- **단위:** 골든 케이스 1건 = 사용자 조항 1개 = 독립 검색 질의.
- **경로:** `user_clause` → retriever(±reranker). 분류는 `review_contract([조항 1개])`.
- **측정:** Recall@k · MRR · **ablation 4변형** · 이탈 분류 P/R · 독소 P/R.
- **함정 집중:** paraphrase / contradiction / partial (검색이 틀리기 쉬운 케이스).

### 트랙 B — 실제 계약서 (스코프 확정: MISSING Recall + 강건성, **전조항 이탈 P/R 라벨링은 안 함**)
- **단위:** 계약서 문서 1건(HWP/PDF 원본).
- **경로:** `KordocParser().parse(file_path)` → **`review_contract` 전체 파이프** (server.py 와 동일 경로 그대로 재사용 — 지름길 없이 실제 파싱 단계까지 검증).
- **측정(정량, 유일):** **MISSING Recall** — `review_contract` 가 낸 MISSING `clause_id` 집합 vs 사람이 컨펌한 `expected_missing` → `metrics.precision_recall` 재사용.
- **측정(정성):** **강건성 스팟체크** — 파싱 성공 여부·조항별 deviation 분포·NO_MATCH 폭주 여부를 사람이 결과 덤프를 훑어 확인. 정량 지표 없음.
- **스코프 축소 이유:** Track A(합성 92건)가 이미 검색·이탈·독소 P/R 을 통계적으로 커버한다. Track B 의 고유 가치는 딱 두 가지 — ① 합성셋은 구조적으로 못 재는 **MISSING**, ② 진짜 HWP/PDF 가 실전 파싱을 안 깨는지. 전 조항 이탈 라벨링은 노력 대비 얻는 정보가 적어 제외.
- **선행:** 실제 계약서 문서 확보(아래 §실행 계획 1번, 팀 수동 작업).

### 트랙 B 실행 계획

| # | 작업 | 산출물 | 담당 |
| --- | --- | --- | --- |
| 1 | 실계약 문서 확보 + 배치 | `src/eval/golden_b/raw/*.hwp\|pdf` (contract_type별 최소 2~3건 권장) | 팀(수동) |
| 2 | 디렉토리·라벨 스키마 확정 | `src/eval/golden_b/{raw/, labels/}` + `labels/<contract_id>.json` (아래 §스키마) | 완료(본 문서) |
| 3 | MISSING 후보 덤프 스크립트 | `src/eval/dump_review_b.py` — `parse_contract`+`review_contract` 를 실문서에 돌려 파싱 결과 미리보기·MISSING 후보·전체 `DeviationResult` 를 사람이 보기 좋게 출력 | 구현 대상 |
| 4 | 사람 컨펌 | 3의 출력에서 MISSING 후보를 확인/수정해 `labels/<contract_id>.json` 의 `expected_missing` 에 반영 (문서당 ~5분, **처음부터 라벨을 쓰는 게 아니라 시스템 제안을 컨펌**) | 팀(수동) |
| 5 | MISSING Recall 평가 함수 | `src/eval/run_eval.py` 에 `evaluate_missing_recall()` 추가 — `labels/*.json` 로드 → 문서별 `review_contract` 실행 → MISSING id 집합 vs `expected_missing` → `metrics.precision_recall` | 구현 대상 |
| 6 | 강건성 스팟체크 | 3번 스크립트의 전체 결과 덤프를 사람이 훑어 이상 징후 확인 (문서당 ~5분) | 팀(수동) |
| 7 | 문서화 | 본 절 갱신(완료) + 결정 로그 세션 3 추가 | 완료 |

### 라벨 스키마 (계약 단위 — 트랙 B)
```jsonc
// src/eval/golden_b/labels/c01.json
{
  "contract_id": "c01",
  "contract_type": "SW_FREELANCE",
  "doc_path": "raw/c01_실계약.hwp",
  "expected_missing": ["sw_freelance-art18"],   // 사람이 3번 결과 보고 컨펌한 최종 목록
  "note": "손해배상 조항이 계약서 전체에 없음 — 3번 스크립트 MISSING 제안과 일치"
}
```
`raw/`(원본 바이너리)와 `labels/`(정답 JSON)를 분리해 라벨 diff 만 리뷰 가능하게 한다(Track A `golden/*.json` 과 동일 원칙 — 정답은 git 으로 관리·리뷰, 원본은 별도).
> `data/` 에 두지 않는 이유: [data/README.md](../../data/README.md) 가 `data/`를 **표준계약서 정답 코퍼스 전용**으로 스코프를 명시함(`01_raw`~`03_normalized` 전부 표준계약서). 실계약 원본은 eval 전용 픽스처이므로 `src/eval/golden_b/` 가 맞는 위치.

---

## 골든셋 스키마

### 케이스 필드 (조항 단위 — 트랙 A) — [예시](../../src/eval/golden/sw_freelance.example.json)
| 필드 | 의미 |
| --- | --- |
| `case_id` | 케이스 식별자 (이탈·독소 P/R 계산 단위) |
| `contract_type` | 계약 종류 (`SW_FREELANCE` / `SI_SUBCONTRACT` / `SM_SUBCONTRACT`) |
| `user_clause` | 평가용 사용자 조항 본문 (= 검색 질의) |
| `gold_clause_id` | 정답 표준조항 id. **비표준(EXTRA)이면 `null`** |
| `gold_deviation` | `NONE` / `CHANGED` / `EXTRA` (트랙 A엔 `MISSING` 없음) |
| `gold_toxic` | (선택) 독소 패턴 라벨 — **반드시 `ToxicPattern` enum 값** |
| `trap` | 함정 유형 (아래) |
| `note` | 사람용 설명 |

### trap 유형 (정식)
`none` / `paraphrase`(말바꿈) / `reorder`(항·호 순서 뒤바뀜) / `partial`(부분 변경·누락) /
`contradiction`(표준 조항번호를 언급하나 내용은 반대 — 랭킹 교란).
> `reorder` 는 스키마엔 정식이나 현재 케이스 0건 → 골든 확장 시 보강 대상(기획서 8.3).

> 계약 단위(트랙 B) 라벨 스키마는 위 §트랙 B 실행 계획에 확정본을 둔다(중복 방지).

---

## 지표 (모두 결정론적 — LLM-judge 금지)
| 축 | 지표 | 함수 | 트랙 |
| --- | --- | --- | --- |
| 검색 품질 | `Recall@k` · `MRR` | `metrics.recall_at_k` / `mrr` | A |
| 이탈 탐지 | `Precision` / `Recall` | `metrics.precision_recall` | A |
| 독소 탐지 | `Precision` / `Recall` | `metrics.precision_recall` | A |
| **ablation** | 위 지표 × 4변형 | `ablation.run_ablation` | A |
| **MISSING Recall** | `Precision` / `Recall` | `metrics.precision_recall` | B |

---

## Driver 구현 ([src/eval/run_eval.py](../../src/eval/run_eval.py) — 통합/수동, 단위테스트 밖)

> 전제: `just build-db` 로 Chroma 인덱스 존재. `eval/` 가 `src/` 하위로 이동하면서
> `setuptools packages`·pytest `pythonpath` 는 `["src"]` 로 정리됨(더는 루트 `"."` 불필요).
> 어댑터 싱글턴 사용: `from adapter import vector, reranker, db`.
> 표준조항 로드는 [server.py](../../src/server/server.py) `_load_standards(ct)` 패턴을 그대로 재사용(`_load_standards`).

### A-1. 검색 + ablation — `build_cases` / `build_cases_by_variant`
`gold_clause_id != null` 케이스만 사용(EXTRA 는 검색 정답 없음 → 집계 제외).
**질의별 개별 호출이 아니라 `search_many`/`rerank_many` 배치**로 변형별 `{retrieved_ids, gold_id}` cases 를 만든다
(07-01 §7 — 임베딩 왕복을 N회→1회로 줄이는 취지와 동일. 초판은 질의별 루프로 짰다가 CPU 다건 처리가 지나치게
느려 배치로 재작성함 — 실측: 92건 개별 호출은 20분+ 실행에도 미완주, 배치는 같은 작업량을 사실상 즉시 처리).

| variant | 만드는 법 |
| --- | --- |
| `bm25` / `dense` / `hybrid` | `vector.search_many(col, queries, search_type=variant, metadata_filter={"contract_type": ct}, top_k=k)` |
| `hybrid_rerank` | `hybrid` 로 넉넉히(pool≈k×4) `search_many` 후 `reranker.rerank_many(queries, pools, top_k=k)` |

→ `cases_by_variant` → `run_ablation(cases_by_variant, k)` → 변형 비교표.
**가설:** paraphrase/contradiction 에서 `bm25` < `dense/hybrid` ≤ `hybrid_rerank`.

### A-2/A-3. 이탈·독소 분류 P/R — `review_golden_clauses` + `deviation_precision_recall` / `toxic_precision_recall`
계약 유형별로 골든 조항 **전체를 한 번에** `review_contract(clauses, ct, retriever=vector, reranker=reranker, grounder=NullGrounder(), ...)` 에 태운다
(조항별 개별 호출은 배치 크기가 항상 1이 되어 내부 배치화 이점이 사라짐 — A-1과 같은 이유로 배치 채택).
반환된 결과 중 `user_clause` 텍스트가 골든의 `user_clause` 와 일치하는 항목만 case_id 에 매핑하고,
매칭 안 된 표준조항(MISSING, `user_clause=""`)은 자연히 제외한다. `grounder` 는 평가 목적상 법령 근거가
불필요하므로(외부 korean-law-mcp 호출·네트워크 의존 제거) driver 전용 `NullGrounder`(no-op)를 주입한다.
- 이탈(이진, 주 지표): `predicted = {case_id | deviation != NONE}` vs `gold = {case_id | gold_deviation != "NONE"}` → `metrics.precision_recall`.
- 독소: `predicted = {case_id | toxic_patterns 비어있지 않음}` vs `gold = {case_id | gold_toxic 존재}` → `metrics.precision_recall`.

### 실행
```bash
uv run python src/eval/run_eval.py   # just build-db 선행 필요. CPU 추론이라 수 분 소요될 수 있음.
```
> `-m eval.run_eval` 은 `eval` 패키지가 `src/` 하위로 이동하면서 루트에서 더는 못 찾음(`ModuleNotFoundError`) —
> 다른 pipe 스크립트(`0.migrate.py`·`build_index.py`)와 동일하게 **직접 스크립트 실행** 컨벤션을 따른다.

`main()` 은 골든 92건 전체를 로드해 A-1 ablation 표와 계약 유형별 A-2/A-3 Precision/Recall 을 출력한다.

---

## 통과할 테스트 (순수 함수 — 이미 통과)
- [tests/eval/test_metrics.py](../../tests/eval/test_metrics.py) ✅
- [tests/eval/test_run_eval.py](../../tests/eval/test_run_eval.py) ✅
- [tests/eval/test_ablation.py](../../tests/eval/test_ablation.py) ✅
> Driver 는 외부 인덱스 의존이라 단위테스트 대상 아님 — build-db 후 통합/수동 실행으로 검증.

## 완료 조건 (DoD)
- [x] `tests/eval/` 3파일 통과 (순수 집계)
- [x] 합성 골든셋 92건 (함정 포함) · 독소 라벨 enum 정합
- [x] Driver 구현 — rerank 포함 4변형 cases 생성, 배치화 (A-1)
- [x] 이탈 분류 P/R 하니스 (A-2) · 독소 P/R 하니스 (A-3) 구현
- [ ] `just build-db` 후 트랙 A 전체 통합 실행 리포트 1회 — **실행 대기**(`uv run python src/eval/run_eval.py`)
- [ ] ablation 표 수치 확인: 4변형 × (Recall@k, MRR) → BM25 대비 hybrid/rerank 우위가 수치로
- [ ] 실측 후 필요 시 `match_threshold`/`change_threshold`/`toxic_threshold` 캘리브레이션 (07-01 후속 미결)
- [ ] **LLM-judge 금지** — 결정론적 계산만 (AGENTS.md 규칙 #5)
- [ ] 트랙 B 1~7번 실행 계획 진행 — 문서 확보(팀) → 덤프 스크립트·MISSING Recall 함수(구현) → 사람 컨펌(팀)

## 참고
- 📖 [src/eval/README.md](../../src/eval/README.md) — 평가 철학·골든셋 포맷·지표별 사용법 (필독)
- 결정 배경: [07-01 결정 로그](../dicision/07-01.md) (매칭 불변식·ablation 스위치), 기획서 8장. 트랙 B 스코프 확정(MISSING Recall + 강건성 스팟체크로 축소)은 본 문서 §트랙 B 가 단일 진실원.
- 트랙 A driver 는 B(인덱스)·C(검색) 작업물 위에서 이미 동작 확인됨 — 남은 건 실행해서 수치를 뽑는 것.
