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

def binary_scores(predicted_ids: Set[str], gold_ids: Set[str], universe: Set[str]) -> Dict[str, float]:
    """precision_recall 을 참음성(TN)까지 확장한 혼동행렬 기반 지표.

    universe = 채점 대상 전체(예: 검토된 case_id 집합). 이 안에서만 TN 을 센다.
    precision·recall 만으로는 '모든 조항을 양성으로 찍는' 축퇴를 잡지 못한다
    (그 경우 recall 은 자명하게 1.0). specificity(=TN/(TN+FP)) 를 함께 보면
    정상 케이스를 정상으로 거르는 능력(참음성)이 드러난다.
    반환: precision·recall·specificity·accuracy·f1 + 원시 카운트(tp/fp/fn/tn).
    """
    predicted = predicted_ids & universe
    gold = gold_ids & universe
    tp = len(predicted & gold)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    tn = len(universe) - tp - fp - fn

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    accuracy = (tp + tn) / len(universe) if universe else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "precision": precision, "recall": recall, "specificity": specificity,
        "accuracy": accuracy, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }