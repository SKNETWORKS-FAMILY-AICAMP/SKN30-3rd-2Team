"""
[담당: 팀원 D] 검색/이탈 탐지 품질 지표 (LLM 없이 결정론적 계산, 기획서 8.2)

규격(통과해야 할 테스트): tests/eval/test_metrics.py
모두 순수 함수입니다. run_eval·ablation 이 이 함수들을 재사용합니다.
"""
from typing import List, Tuple, Set, Dict

def recall_at_k(retrieved_ids: List[str], gold_id: str, k: int) -> float:
    """정답이 상위 k 안에 있으면 1.0, 없으면 0.0."""
    if not gold_id:
        return 0.0
    return 1.0 if gold_id in retrieved_ids[:k] else 0.0

def reciprocal_rank(retrieved_ids: List[str], gold_id: str) -> float:
    """정답 순위의 역수(1/rank). 없으면 0.0."""
    if not gold_id or gold_id not in retrieved_ids:
        return 0.0
    rank = retrieved_ids.index(gold_id) + 1
    return 1.0 / rank

def mrr(cases: List[Tuple[List[str], str]]) -> float:
    """여러 (검색결과, 정답) 쌍에 대한 reciprocal_rank 평균."""
    if not cases:
        return 0.0
    total_rr = sum(reciprocal_rank(retrieved, gold) for retrieved, gold in cases)
    return total_rr / len(cases)

def precision_recall(predicted_ids: Set[str], gold_ids: Set[str]) -> Dict[str, float]:
    """이탈 탐지 정밀도/재현율. {"precision": float, "recall": float}."""
    if not predicted_ids and not gold_ids:
        return {"precision": 1.0, "recall": 1.0}
    
    true_positives = len(predicted_ids.intersection(gold_ids))
    
    precision = true_positives / len(predicted_ids) if predicted_ids else 0.0
    recall = true_positives / len(gold_ids) if gold_ids else 0.0
    
    return {"precision": precision, "recall": recall}