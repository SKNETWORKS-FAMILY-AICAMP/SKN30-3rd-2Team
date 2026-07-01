# eval/ — 평가 하니스 (LLM 없이 정량 측정)

"조항 몇십 개면 체크리스트로 되지 않나?"라는 반론을 **주장이 아니라 수치로** 깨는 것이 이 폴더의 목표입니다. 모든 지표는 **결정론적·재현 가능**하게 계산하며, **LLM-judge는 쓰지 않습니다**(AGENTS.md 규칙 #5).

## 무엇을 측정하나 — 두 축 + ablation

| 축 | 지표 | 질문 |
| --- | --- | --- |
| **검색 품질** | `Recall@k`, `MRR` | 사용자 조항에 맞는 표준조항을 상위 k 안에 잘 찾아오는가 |
| **이탈 탐지** | `Precision` / `Recall` | 짚어낸 이탈 중 진짜 비율 / 진짜 이탈 중 짚어낸 비율 |
| **ablation (8.5)** | 위 지표 × 4변형 | **RAG가 필요한가**를 증명하는 대표 결과물 |

**ablation 4변형:** `BM25-only` / `dense-only` / `hybrid` / `hybrid+reranker`.
기대 결과 — 말바꿈·순서 뒤집기 함정에서 BM25는 실패하고 dense/hybrid가 잡아내는 비율을 수치로 제시 → RAG 정당성이 경험적으로 증명됩니다.

## 구성

| 파일 | 역할 | 테스트 |
| --- | --- | --- |
| [metrics.py](metrics.py) | `recall_at_k` · `reciprocal_rank` · `mrr` · `precision_recall` · `binary_scores`(참음성·특이도 포함) (순수 함수) | [test_metrics.py](../tests/eval/test_metrics.py) |
| [run_eval.py](run_eval.py) | `evaluate(cases, k)` 순수 집계 + **Driver `main(k, version)`** (골든 실행·`vN_result.md` 생성) | [test_run_eval.py](../tests/eval/test_run_eval.py) |
| [ablation.py](ablation.py) | `run_ablation(cases_by_variant, k)` — 변형별 비교표 (run_eval 재사용) | [test_ablation.py](../tests/eval/test_ablation.py) |
| `golden/` | 골든셋 정답지 + 버전별 결과·리뷰 (아래 협업 워크플로우) | — |

> 재사용 사슬: **ablation → run_eval → metrics**. 같은 계산을 두 번 구현하지 마세요.

---

## 협업 워크플로우 — 골든셋 버전 루프 (v1 → v2 → …)

골든셋은 한 번에 완성하지 않는다. **버전(vN)을 올리며 "제작 → 실행 → 리뷰 → 개선"을 반복**해
고도화한다. 각 버전은 `golden/` 안에서 세 종류 파일로 구성되며, **버전 접두사(`vN_`)로 스코프**되어
이전 버전과 같은 폴더에 공존해도 섞이지 않는다.

| 파일 | 무엇 | 누가 / 어떻게 |
| --- | --- | --- |
| `golden/vN_<type>.json` | 골든셋 정답 데이터 (계약유형별: `sw_freelance`·`si_subcontract`·`sm_subcontract`) | **사람**이 제작·라벨 (git 커밋 → PR 리뷰) |
| `golden/vN_result.md` | 평가 지표 결과 (A-1 검색 ablation + A-2/A-3 이탈·독소 분류) | **자동** — `run_eval.main()` 이 실행 끝에 생성 |
| `golden/vN_review.md` | 리뷰: 근본 원인 + 골든셋 강·약점 + 다음 버전 반영점 | **리뷰어(사람/AI)** 가 작성 |

### 한 사이클
1. **(제작)** `golden/vN_<type>.json` 작성/수정.
2. **(실행)** 아래 명령 → 로그 출력과 함께 `vN_result.md` 자동 생성.
3. **(리뷰)** 결과를 보고 `vN_review.md` 에 원인·강약점·개선 체크리스트 기록.
4. **(버전업)** 리뷰를 반영해 `v(N+1)_<type>.json` 제작 → 1로. 이전 버전 파일은 **이력으로 보존**.

```bash
# 드라이버 인자: python -m eval.run_eval [a|b] [version]   (트랙 생략 시 a, 버전 생략 시 최신)
PYTHONPATH=src python -m eval.run_eval               # 트랙 A, 최신 버전, 로컬 모델
APP_ENV=prod PYTHONPATH=src python -m eval.run_eval a v2   # 트랙 A, v2, RunPod
```
- 버전 인자를 생략하면 **가장 높은 `vN`** 을 자동 선택한다.
- `APP_ENV=prod` 면 RunPod API 어댑터, 미설정(`local`) 이면 로컬 모델을 쓴다(둘 다 인덱스는 로컬 Chroma).
- 선행: `just build-db` 로 인덱스가 준비돼 있어야 한다.

> 결과 해석 팁: `Recall=1.0` 인데 `특이도=0` 이면 성능이 좋은 게 아니라 **모든 조항을 양성으로 찍는
> 축퇴**다. 반드시 특이도·TN 을 함께 보고, 원인은 `vN_review.md` 에 남긴다.

### 트랙 B — 실계약 문서 (같은 버전 루프, 단 3가지 조정)

트랙 B(실계약 HWP/PDF 문서 단위)도 **같은 버전 루프**를 쓴다. 파일은 `golden_b/` 아래:

| 파일 | 무엇 | 누가 |
| --- | --- | --- |
| `golden_b/raw/*.hwp\|pdf` | 실계약 원본(바이너리) | **사람**(팀 수동 확보) |
| `golden_b/labels/vN_<id>.json` | 계약 단위 정답(`expected_missing` 등, 스키마: [D_eval.md](../docs/tasks/D_eval.md) §라벨 스키마) | **사람**(아래 순환 편향 주의) |
| `golden_b/vN_b_result.md` | MISSING Recall(자동) + 강건성 스팟체크(사람) | 하이브리드 |

```bash
# 문서 검토 덤프(사람 확인용) + MISSING Recall 계산·저장을 함께 수행
APP_ENV=prod PYTHONPATH=src python -m eval.run_eval b        # 트랙 B, 최신 버전
```

**트랙 A와 다른 3가지 (반드시 유의):**
1. **result.md 가 정량+정성 하이브리드다.** 정량 지표는 **MISSING Recall 하나뿐**(자동 생성)이고, 파싱 성공·deviation 분포·NO_MATCH 폭주 등 **강건성은 정성 스팟체크**(사람이 result.md 하단 섹션을 채움). 완전 자동이 아니다.
2. **표본이 2~3건이라 수치는 '방향 참고'다.** 문서 한 건만 뒤집혀도 크게 흔들린다. **지표를 최적화 목표로 삼지 말 것.** 트랙 B의 진짜 가치는 "실제 문서가 파싱을 깨뜨리는가"라는 정성 신호.
3. **⚠️ 순환 편향 방어(가장 중요).** 라벨링은 "처음부터 쓰는" 게 아니라 **시스템이 제안한 MISSING 을 사람이 컨펌**하는 방식이라, 그대로 두면 MISSING Recall 이 "시스템이 자기 자신과 일치하는 정도"를 재게 되어 **낙관 편향**된다(트랙 A의 `R=1.0/특이도=0`과 같은 함정). 컨펌할 때 **시스템이 제안하지 못한 누락도 사람이 독립적으로 찾아** `expected_missing` 에 넣어야 한다.

**한 사이클(B):** ① `raw/` 에 문서 확보 → ② `run_eval b` 로 덤프+지표 → ③ 덤프의 MISSING 후보를 컨펌(+독립 누락 추가)해 `labels/vN_<id>.json` 갱신 → ④ `vN_b_result.md` 의 강건성 섹션 작성 → ⑤ 리뷰 기록 → ⑥ 버전업.

---

## 골든셋 (정답지)

### 형태 (기획서 8.1)
**(사용자 조항 ↔ 정답 표준조항) 쌍 + 이탈 라벨.** 예시: [golden/v1_sw_freelance.json](golden/v1_sw_freelance.json)

### 케이스 필드
| 필드 | 의미 |
| --- | --- |
| `case_id` | 케이스 식별자 (이탈 precision/recall 계산 단위) |
| `contract_type` | 계약 종류 (`SW_FREELANCE` 등) |
| `user_clause` | 평가용 사용자 조항 본문 (= 검색 질의) |
| `gold_clause_id` | 정답 표준조항 id. **비표준(EXTRA)이면 `null`** |
| `gold_deviation` | `NONE` / `CHANGED` / `EXTRA` (조항 단위). `MISSING` 은 계약 단위 → 아래 참조 |
| `gold_toxic` | (선택) 독소 패턴 라벨 — **반드시 `ToxicPattern` enum 값** (`IP_TOTAL_FREE` 등) |
| `trap` | `none` / `paraphrase`(말바꿈) / `reorder`(순서) / `partial`(부분변경) / `contradiction`(조항번호 언급+내용 반대) |
| `note` | 사람용 설명 |

### 지표별 사용법
- **Recall@k / MRR:** `user_clause`를 retriever에 넣어 얻은 `retrieved_ids`를 `gold_clause_id`와 비교. (`gold_clause_id=null`인 EXTRA 케이스는 "표준에 매칭되면 안 됨"으로 검증)
- **이탈 Precision/Recall:** 시스템이 이탈로 플래그한 `case_id` 집합 vs `gold_deviation != NONE`인 정답 집합을 `precision_recall`로 비교.

### MISSING 은 계약 단위로 평가
`MISSING`(누락)은 개별 조항 질의가 아니라 **"표준에는 있는데 사용자 계약서 전체에 없음"** 이라 계약 단위로 측정합니다.
→ 합성 계약서에서 **일부러 뺀 표준조항 id 목록**을 정답으로 두고, 시스템의 MISSING 출력과 비교합니다.
```jsonc
// 계약 단위 골든셋(확장 예)
{ "contract_id": "c01", "contract_type": "SW_FREELANCE",
  "clauses": ["g01", "g05", ...],            // 위 케이스 id 참조
  "expected_missing": ["sw_freelance-art18"] // 손해배상 조항을 일부러 누락시킨 합성 계약
}
```

### 제작 가이드 (기획서 8.3 — 함정을 많이)
- **합성:** 표준조항을 변형(말바꿈/기간·금액 변경/순서 뒤집기/부분 삭제)해 만든다.
- **실제:** 실제 샘플 계약서에 사람이 정답을 라벨링한다.
- **함정 비중을 높인다:** 검색이 틀리기 쉬운 `paraphrase`·`reorder`·`partial`을 의도적으로 많이 넣어야 ablation에서 RAG의 가치가 드러난다.

> 현재 합성 골든셋 **v1** 3종 92건(`v1_sw_freelance` 17 · `v1_si_subcontract` 25 · `v1_sm_subcontract` 50).
> **평가는 두 트랙으로 나뉜다** — 트랙 A(합성 조항 단위: 검색·분류·독소·ablation)와
> 트랙 B(실제 계약서 = 계약 단위: E2E·MISSING, 현재 보류). 상세·Driver 규격은
> [docs/tasks/D_eval.md](../docs/tasks/D_eval.md) 를 단일 진실원으로 삼는다.

---

## Driver — 골든셋을 실제 검색에 흘려보내기

`run_eval.evaluate` / `run_ablation` 은 **이미 검색된** cases(`{retrieved_ids, gold_id}`)를 받는 **순수 집계** 함수입니다. 그 cases 를 만들려면 골든셋의 `user_clause` 를 **실제 retriever 에 돌려 `retrieved_ids` 를 뽑는** 글루가 필요합니다. 이게 **driver** 이고, `run_eval.py` / `ablation.py` 의 CLI(`if __name__ == "__main__"`) 부분에 둡니다. (테스트 밖 · 통합 · B의 인덱스 필요)

### 책임
골든셋 + 검색 변형 → cases. `adapter.vector.search` (+ `reranker`) 를 사용:
```python
# eval/run_eval.py — driver 부분 (방향 스케치, 구현은 팀원 D)
from adapter import vector, reranker

def build_cases(golden: list[dict], search_type: str, k: int, contract_type: str) -> list[dict]:
    cases = []
    for g in golden:
        if g["gold_clause_id"] is None:      # EXTRA(비표준): 검색 정답이 없음 → 별도 검증으로
            continue
        hits = vector.search(
            "standard_clauses", g["user_clause"],
            search_type=search_type, top_k=k,
            metadata_filter={"contract_type": contract_type},
        )
        cases.append({"retrieved_ids": [h["id"] for h in hits], "gold_id": g["gold_clause_id"]})
    return cases
```

### 4변형을 만드는 법 (ablation 용)
| variant | 만드는 법 |
| --- | --- |
| `bm25` | `vector.search(..., search_type="bm25")` |
| `dense` | `vector.search(..., search_type="dense")` |
| `hybrid` | `vector.search(..., search_type="hybrid")` |
| `hybrid_rerank` | `hybrid` 로 넉넉히 뽑은 뒤 `reranker.rerank(user_clause, hits)[:k]` 로 재정렬 |

### 전체 흐름
```
골든셋 로드 → 변형별 build_cases() → cases_by_variant
        → run_ablation(cases_by_variant, k) → 변형 비교표 출력
```

### 주의
- **EXTRA(`gold_clause_id=null`)** 케이스는 검색 정답이 없으므로 Recall@k/MRR 집계에서 제외하고, *"표준에 매칭되면 안 됨"* 은 이탈 평가 쪽에서 검증.
- driver 는 외부 인덱스에 의존하므로 **단위테스트 대상이 아님**(집계 순수함수만 테스트). driver 검증은 인덱스 빌드 후 수동/통합 실행.
- 선행: `just build-db` 로 Chroma 인덱스가 있어야 동작.

---

## 실행

```bash
uv run pytest tests/eval/        # 순수 함수 규격부터 통과 (의존성 0 — 지금 시작 가능)
# 실제 골든셋 평가/ablation 은 B의 인덱스 + C의 검색이 연결된 뒤 통합 실행
```

## 규칙
- **LLM-judge 금지** — 모든 점수는 결정론적 계산만.
- metrics 외 중복 구현 금지 (run_eval·ablation 은 metrics 재사용).
- 골든셋 JSON 은 정답 데이터이므로 **git 커밋**해 PR로 리뷰.
