"""
[작업 규격 · 담당: 팀원 D] eval.run_eval — 골든셋으로 검색/이탈 탐지 평가

구현 대상: eval/run_eval.py
  - 순수 집계 함수(테스트 대상): 이미 검색된 결과 케이스들 → 지표 묶음
        evaluate(cases: list[dict], k: int = 5) -> dict
            cases 각 항목: {"retrieved_ids": list[str], "gold_id": str}
            반환: {"recall@k": float, "mrr": float, "n": int}
  - CLI 부분(테스트 밖): 골든셋을 review 파이프에 통과시켜 retrieved_ids 를 모으고
    위 evaluate 로 집계해 리포트 출력. (실제 인덱스 필요 → 통합/수동)

eval.metrics 의 recall_at_k / mrr 를 재사용합니다. (중복 구현 금지)

👉 구현을 시작하면 pytestmark(skip) 줄을 삭제하세요.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TDD 규격 — 담당: 팀원 D. 구현 시작 시 이 줄 삭제")


def test_evaluate_집계():
    from eval.run_eval import evaluate
    cases = [
        {"retrieved_ids": ["a", "b", "c"], "gold_id": "a"},  # rr=1.0, recall@2=1
        {"retrieved_ids": ["x", "y", "z"], "gold_id": "z"},  # rr=1/3, recall@2=0
    ]
    report = evaluate(cases, k=2)
    assert report["n"] == 2
    assert report["recall@k"] == pytest.approx(0.5)              # 1/2 케이스만 상위2 적중
    assert report["mrr"] == pytest.approx((1.0 + 1 / 3) / 2)


def test_evaluate_빈_케이스():
    from eval.run_eval import evaluate
    report = evaluate([], k=5)
    assert report["n"] == 0
