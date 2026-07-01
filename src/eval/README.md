# eval/ — 평가 하니스 (LLM 없이 정량 측정)

> **담당: 팀원 D** · 기획서 8장

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
| [metrics.py](metrics.py) | `recall_at_k` · `reciprocal_rank` · `mrr` · `precision_recall` (순수 함수) | [test_metrics.py](../tests/eval/test_metrics.py) |
| [run_eval.py](run_eval.py) | `evaluate(cases, k)` — 골든셋 검색 결과를 집계 (metrics 재사용) | [test_run_eval.py](../tests/eval/test_run_eval.py) |
| [ablation.py](ablation.py) | `run_ablation(cases_by_variant, k)` — 변형별 비교표 (run_eval 재사용) | [test_ablation.py](../tests/eval/test_ablation.py) |
| `golden/` | 골든셋(정답지) JSON | — |

> 재사용 사슬: **ablation → run_eval → metrics**. 같은 계산을 두 번 구현하지 마세요.

---

## 골든셋 (정답지)

### 형태 (기획서 8.1)
**(사용자 조항 ↔ 정답 표준조항) 쌍 + 이탈 라벨.** 예시: [golden/sw_freelance.example.json](golden/sw_freelance.example.json)

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

> 현재 합성 골든셋 3종 92건(sw_freelance 17 · si_subcontract 25 · sm_subcontract 50).
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
