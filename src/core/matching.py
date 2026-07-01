import math
from typing import List, Tuple, Optional
from contracts.models import StandardClause


def sigmoid(x: float) -> float:
    """
    크로스 인코더(리랭커)의 raw 점수(로짓)를 0~1 범위의 정규화 점수로 변환합니다.

    리랭커 어댑터(BgeReranker)는 CrossEncoder.predict의 raw 로짓을 rerank_score로 반환하므로,
    스케일이 불명확합니다(음수~양수). 이를 그대로 match_threshold(0.5)와 비교하면 의미가 없어,
    로짓 0 → 0.5 로 매핑되는 sigmoid를 적용해 "threshold 0.5 = 모델이 양(+)의 판단" 을 유지합니다.
    큰 음수 입력에서의 math.exp 오버플로를 피하기 위해 부호에 따라 분기합니다.
    """
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


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

def roll_up_sub_chunks(
    sub_chunk_results: List[Tuple[str, float]]
) -> Tuple[Optional[str], float]:
    """
    서브청크 검색 결과 목록을 parent_clause_id 별로 그룹화하여
    각 부모의 Max Score를 계산하고, 가장 점수가 높은 부모 조항 ID와 그 점수를 반환합니다.

    Args:
        sub_chunk_results (List[Tuple[str, float]]): 서브청크 수준의 검색 및 리랭크 결과 목록.
            각 튜플은 (부모 조항 ID `parent_clause_id`, 유사도 점수 `score`)로 구성됩니다.
            예: [("sw_freelance-art58", 0.85), ("sw_freelance-art58", 0.92), ("sw_freelance-art6", 0.78)]

    Returns:
        Tuple[Optional[str], float]: 가장 높은 Max Score를 기록한 부모 조항 ID와 해당 점수의 튜플.
            - 형식: (최적의 parent_clause_id, 최고 유사도 점수)
            - 입력 결과가 비어 있거나 매칭되는 부모 조항이 없는 경우 (None, 0.0)를 반환합니다.
    """
    if not sub_chunk_results:
        return None, 0.0
        
    # parent_clause_id별 최댓값(Max Score) 집계
    parent_max_scores = {}
    for parent_id, score in sub_chunk_results:
        if parent_id not in parent_max_scores:
            parent_max_scores[parent_id] = score
        else:
            parent_max_scores[parent_id] = max(parent_max_scores[parent_id], score)
            
    if not parent_max_scores:
        return None, 0.0
        
    # 가장 높은 점수를 가진 부모 조항 선정
    best_parent_id = max(parent_max_scores, key=parent_max_scores.get)
    return best_parent_id, parent_max_scores[best_parent_id]


def check_coverage(
    standard_ids: List[str],
    similarity_matrix: List[List[float]],
    threshold: float
) -> Tuple[bool, List[str]]:
    """
    표준 서브청크들과 사용자 서브청크들 간의 유사도 매트릭스를 기반으로
    각 표준 서브청크가 커버되었는지 검사합니다.

    Args:
        standard_ids (List[str]): 검사 대상이 되는 표준 서브청크 ID 목록 (길이 M).
        similarity_matrix (List[List[float]]): 유사도 매트릭스.
            크기는 M x N 이며, similarity_matrix[i][j]는 i번째 표준 서브청크와 j번째 사용자 서브청크 간의 유사도 점수입니다.
        threshold (float): 커버된 것으로 간주할 최소 유사도 임계치.

    Returns:
        Tuple[bool, List[str]]: (모든 표준 서브청크가 커버되었는지 여부, 미커버된 표준 서브청크 ID 목록)
            - True, [] : 모든 표준 서브청크가 최소 1개 이상의 사용자 서브청크에 의해 커버됨.
            - False, [uncovered_id, ...] : 커버되지 못한 표준 서브청크가 존재함.
    """
    if not standard_ids:
        return True, []

    uncovered_ids = []
    for i, std_id in enumerate(standard_ids):
        # i번째 표준 서브청크의 사용자 서브청크들과의 유사도 목록
        scores = similarity_matrix[i]

        # 임계값 이상인 매칭이 하나라도 있는지 확인
        is_covered = any(score >= threshold for score in scores) if scores else False

        if not is_covered:
            uncovered_ids.append(std_id)

    is_fully_covered = len(uncovered_ids) == 0
    return is_fully_covered, uncovered_ids
