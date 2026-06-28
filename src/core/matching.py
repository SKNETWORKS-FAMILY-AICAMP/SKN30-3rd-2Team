from typing import List, Tuple, Optional
from contracts.models import StandardClause

def select_best_match(
    candidates: List[Tuple[StandardClause, float]], 
    threshold: float
) -> Tuple[Optional[StandardClause], float]:
    """
    유사도 점수(리랭커 점수 등)가 가장 높은 후보를 선택하되, 
    임계치(threshold) 미만인 경우 매칭을 인정하지 않습니다.
    
    Args:
        candidates (List[Tuple[StandardClause, float]]): (표준 조항, 유사도 점수) 리스트
        threshold (float): 최소 매칭 인정 점수 임계치
        
    Returns:
        Tuple[Optional[StandardClause], float]: 선택된 표준 조항(없으면 None)과 점수
    """
    if not candidates:
        return None, 0.0
        
    # 점수 기준 내림차순 정렬
    sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
    best_candidate, best_score = sorted_candidates[0]
    
    if best_score >= threshold:
        return best_candidate, best_score
    else:
        return None, 0.0
