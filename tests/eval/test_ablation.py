"""
[작업 규격 · 담당: 팀원 D] eval.ablation — 리트리벌 변형군 비교 (기획서 8.5, 필수)

"RAG가 필요한가"를 주장이 아니라 수치로 증명하는 대표 결과물.
같은 골든셋에서 4가지를 비교: BM25-only / dense-only / hybrid / hybrid+reranker.

구현 대상: eval/ablation.py
  - 순수 집계 함수(테스트 대상):
        run_ablation(cases_by_variant: dict[str, list[dict]], k: int = 5) -> dict[str, dict]
            입력: {"bm25": [cases...], "dense": [...], "hybrid": [...], "hybrid_rerank": [...]}
                  (각 cases 항목은 run_eval 과 동일: {"retrieved_ids", "gold_id"})
            반환: {variant: {"recall@k": float, "mrr": float, "n": int}}
  - CLI 부분(테스트 밖): 각 변형으로 실제 검색을 돌려 cases_by_variant 를 만든 뒤 위 함수로 집계.

eval.run_eval.evaluate 를 변형별로 호출해 재사용합니다. (중복 구현 금지)

👉 구현을 시작하면 pytestmark(skip) 줄을 삭제하세요.
"""
import pytest

VARIANTS = ["bm25", "dense", "hybrid", "hybrid_rerank"]


def test_변형군마다_지표_생성():
    from eval.ablation import run_ablation
    cases_by_variant = {
        "bm25": [{"retrieved_ids": ["x", "a"], "gold_id": "a"}],          # rr=1/2
        "dense": [{"retrieved_ids": ["a", "x"], "gold_id": "a"}],         # rr=1
        "hybrid": [{"retrieved_ids": ["a", "x"], "gold_id": "a"}],        # rr=1
        "hybrid_rerank": [{"retrieved_ids": ["a", "x"], "gold_id": "a"}], # rr=1
    }
    table = run_ablation(cases_by_variant, k=1)
    # 4개 변형 모두 결과가 있어야 함
    assert set(table.keys()) == set(VARIANTS)
    # 각 변형은 지표 키를 가짐
    assert table["dense"]["mrr"] == pytest.approx(1.0)
    assert table["bm25"]["mrr"] == pytest.approx(0.5)
    # 말바꿈/순서 케이스에서 dense·hybrid 가 bm25 보다 잘해야 한다는 가설을 수치로 확인
    assert table["hybrid"]["mrr"] >= table["bm25"]["mrr"]
