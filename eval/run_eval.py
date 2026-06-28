"""
[담당: 팀원 D] 골든셋으로 검색/이탈 탐지 평가 (기획서 8)

규격(통과해야 할 테스트): tests/eval/test_run_eval.py
순수 집계 함수 evaluate 는 eval.metrics 를 재사용합니다(중복 구현 금지).
CLI 부분(골든셋 → review 파이프 → retrieved_ids 수집)은 통합/수동 실행입니다.
"""
from typing import List, Dict


def evaluate(cases: List[Dict], k: int = 5) -> Dict:
    """
    검색 결과 케이스들을 지표로 집계합니다.
    cases 각 항목: {"retrieved_ids": list[str], "gold_id": str}
    반환: {"recall@k": float, "mrr": float, "n": int}
    """
    raise NotImplementedError("담당: 팀원 D — tests/eval/test_run_eval.py")
