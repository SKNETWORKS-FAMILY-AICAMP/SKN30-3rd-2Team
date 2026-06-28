"""
[작업 규격 · 담당: 팀원 D] eval.metrics — 검색 품질 지표 (LLM 없이 결정론적 계산)

구현 대상: eval/metrics.py 에 아래 순수 함수들. (기획서 8.2)

    recall_at_k(retrieved_ids: list[str], gold_id: str, k: int) -> float
        정답이 상위 k 안에 있으면 1.0, 없으면 0.0

    reciprocal_rank(retrieved_ids: list[str], gold_id: str) -> float
        정답 순위의 역수(1/rank). 없으면 0.0

    mrr(cases: list[tuple[list[str], str]]) -> float
        여러 (검색결과, 정답) 쌍에 대한 reciprocal_rank 평균

    precision_recall(predicted_ids: set[str], gold_ids: set[str]) -> dict
        이탈 탐지 정밀도/재현율. {"precision": float, "recall": float}
        precision = |pred ∩ gold| / |pred|,  recall = |pred ∩ gold| / |gold|

👉 구현을 시작하면 pytestmark(skip) 줄을 삭제하고 빨강 → 초록으로 만드세요.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TDD 규격 — 담당: 팀원 D. 구현 시작 시 이 줄 삭제")


def test_recall_at_k_정답이_상위k_안():
    from eval.metrics import recall_at_k
    assert recall_at_k(["a", "b", "c"], gold_id="b", k=2) == 1.0


def test_recall_at_k_정답이_k_밖():
    from eval.metrics import recall_at_k
    assert recall_at_k(["a", "b", "c"], gold_id="c", k=2) == 0.0


def test_reciprocal_rank_순위_역수():
    from eval.metrics import reciprocal_rank
    assert reciprocal_rank(["a", "b", "c"], gold_id="b") == pytest.approx(0.5)  # 2번째 → 1/2


def test_reciprocal_rank_정답없으면_0():
    from eval.metrics import reciprocal_rank
    assert reciprocal_rank(["a", "b"], gold_id="z") == 0.0


def test_mrr_여러_쿼리_평균():
    from eval.metrics import mrr
    cases = [(["a", "b"], "a"), (["a", "b"], "b")]  # 1/1, 1/2
    assert mrr(cases) == pytest.approx(0.75)


def test_precision_recall_부분일치():
    from eval.metrics import precision_recall
    # 예측 3개 중 2개 정답, 정답 4개 중 2개 맞춤
    pr = precision_recall(predicted_ids={"a", "b", "x"}, gold_ids={"a", "b", "c", "d"})
    assert pr["precision"] == pytest.approx(2 / 3)
    assert pr["recall"] == pytest.approx(2 / 4)


def test_precision_recall_예측없으면_0():
    from eval.metrics import precision_recall
    pr = precision_recall(predicted_ids=set(), gold_ids={"a"})
    assert pr["precision"] == 0.0
    assert pr["recall"] == 0.0
