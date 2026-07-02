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


# --- 축퇴 경보 (v1 리뷰 §1 사후 조치: recall 1.0 / 특이도 0 오독을 지표 차원에서 차단) ---
def _scores(tp, fp, fn, tn):
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def test_degeneracy_alerts_전부_양성이면_경보():
    from eval.run_eval import degeneracy_alerts
    assert degeneracy_alerts(_scores(tp=5, fp=4, fn=0, tn=0), "이탈") != []


def test_degeneracy_alerts_전부_음성이면_경보():
    from eval.run_eval import degeneracy_alerts
    assert degeneracy_alerts(_scores(tp=0, fp=0, fn=3, tn=4), "독소") != []


def test_degeneracy_alerts_정상_분포면_경보_없음():
    from eval.run_eval import degeneracy_alerts
    assert degeneracy_alerts(_scores(tp=3, fp=1, fn=1, tn=4), "이탈") == []


def test_degeneracy_alerts_빈_집계는_경보_없음():
    from eval.run_eval import degeneracy_alerts
    assert degeneracy_alerts(_scores(tp=0, fp=0, fn=0, tn=0), "이탈") == []


def test_coverage_degeneracy_단일_클래스면_경보():
    from eval.run_eval import coverage_degeneracy_alert
    assert coverage_degeneracy_alert({"CHANGED": 10}) is not None


def test_coverage_degeneracy_혼합_분포면_경보_없음():
    from eval.run_eval import coverage_degeneracy_alert
    assert coverage_degeneracy_alert({"CHANGED": 6, "NONE": 4}) is None


def test_coverage_degeneracy_표본_너무_작으면_판단_보류():
    from eval.run_eval import coverage_degeneracy_alert
    assert coverage_degeneracy_alert({"CHANGED": 2}) is None
