from typing import List, Tuple
from contracts.enums import ToxicPattern

def detect_toxic_patterns(
    matches: List[Tuple[ToxicPattern, float]],
    threshold: float
) -> List[ToxicPattern]:
    """
    [고도화 B: 독소조항 양방향 검색]
    표준 대비 이탈 탐지(사용자→표준 방향)와 별개로, 사용자 조항을
    독소 패턴 코퍼스(data/03_normalized/toxic_patterns.json)에도 매칭하는 역방향 검색입니다.
    "표준에는 없지만 사용자에게 불리한 추가 조항"을 잡아내기 위해 조항 단위 루프에서
    classify_clause_deviation과 병렬로 호출됩니다. 결과는 DeviationResult.toxic_patterns에 담깁니다.

    pipe가 Chroma toxic_patterns 컬렉션에서 검색한 (패턴, 점수) 쌍을 이 함수에 전달하면,
    여기서 임계치 필터링과 점수 내림차순 정렬만 수행합니다.

    Args:
        matches: pipe가 독소 패턴 컬렉션 검색으로 얻은 (ToxicPattern, 유사도 점수) 목록
        threshold: 독소조항으로 인정할 최소 점수

    Returns:
        감지된 독소조항 패턴 목록 (점수 내림차순)
    """
    detected = []
    # 점수가 높은 순으로 정렬
    sorted_matches = sorted(matches, key=lambda x: x[1], reverse=True)
    
    for pattern, score in sorted_matches:
        if score >= threshold:
            detected.append(pattern)
            
    return detected
