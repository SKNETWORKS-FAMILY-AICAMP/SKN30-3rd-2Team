from typing import List, Tuple, Optional
from contracts.models import StandardClause

def select_best_match(
    candidates: List[Tuple[StandardClause, float]],
    threshold: float
) -> Tuple[Optional[StandardClause], float]:
    """
    Chroma 하이브리드 검색이 반환한 top-k 후보 중 리랭커 점수가 가장 높은 표준조항을 선택합니다.
    이 함수는 조항 단위 검토 루프에서 리랭커 결과를 받은 직후 호출되며,
    "이 사용자 조항이 어떤 표준조항과 대응되는가"를 결정하는 관문입니다.

    threshold 미만이면 대응 표준조항이 없다고 판단합니다(→ 후속 classify에서 EXTRA 처리).
    candidates가 비어 있으면 pipe 레이어에서 NO_MATCH로 처리해야 합니다(이 함수의 책임 밖).

    Args:
        candidates: 리랭커가 점수를 매긴 (표준조항, 점수) 후보 목록
        threshold: 매칭으로 인정할 최소 점수 (기본값은 pipe에서 주입)

    Returns:
        (매칭된 표준조항, 점수) — 임계치 미달 또는 후보 없으면 (None, 0.0)
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
