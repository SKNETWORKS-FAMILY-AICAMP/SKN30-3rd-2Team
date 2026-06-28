from typing import List, Tuple
from contracts.enums import ToxicPattern

def detect_toxic_patterns(
    matches: List[Tuple[ToxicPattern, float]],
    threshold: float
) -> List[ToxicPattern]:
    """
    [고도화 B: 독소조항 양방향 검색]
    사용자 조항과 독소조항 패턴셋 간의 매칭 점수를 분석하여 
    임계치(threshold) 이상인 위험한 독소조항 분류 목록을 추출합니다.
    
    Args:
        matches (List[Tuple[ToxicPattern, float]]): (독소 패턴, 매칭 스코어) 후보 리스트
        threshold (float): 독소조항으로 인정할 최소 점수 임계치
        
    Returns:
        List[ToxicPattern]: 감지된 독소조항 패턴 목록
    """
    detected = []
    # 점수가 높은 순으로 정렬
    sorted_matches = sorted(matches, key=lambda x: x[1], reverse=True)
    
    for pattern, score in sorted_matches:
        if score >= threshold:
            detected.append(pattern)
            
    return detected
