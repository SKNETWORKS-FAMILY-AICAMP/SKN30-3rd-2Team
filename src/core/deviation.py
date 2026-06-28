import difflib
from typing import List, Set, Optional
from contracts.enums import Deviation
from contracts.models import StandardClause

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    두 텍스트의 공백을 제거하고 SequenceMatcher를 활용해 유사도 비율을 계산합니다.
    """
    t1 = "".join(text1.split())
    t2 = "".join(text2.split())
    return difflib.SequenceMatcher(None, t1, t2).ratio()

def classify_clause_deviation(
    user_text: str,
    matched_standard: Optional[StandardClause],
    score: float,
    match_threshold: float,
    change_threshold: float = 0.85
) -> Deviation:
    """
    매칭 결과 및 본문 유사도를 바탕으로 조항의 이탈(Deviation) 상태를 분류합니다.
    
    - matched_standard가 없거나 매칭 점수가 임계치 미만: EXTRA (표준 외 추가 조항)
    - 매칭되었으나 본문 내용 일치율이 change_threshold 미만: CHANGED (조항 변경됨)
    - 매칭되었고 본문 내용 일치율이 change_threshold 이상: NONE (이탈 없음)
    """
    if matched_standard is None or score < match_threshold:
        return Deviation.EXTRA
        
    # 본문 텍스트 일치율 비교
    similarity = calculate_text_similarity(user_text, matched_standard.text)
    
    if similarity >= change_threshold:
        return Deviation.NONE
    else:
        return Deviation.CHANGED

def detect_missing_clauses(
    all_standard_clauses: List[StandardClause],
    matched_clause_ids: Set[str]
) -> List[StandardClause]:
    """
    기준이 되는 모든 표준 조항 중에서 사용자 조항에 단 한 번도 매칭되지 않은 
    표준 조항들을 발췌하여 MISSING(누락) 목록으로 반환합니다.
    """
    missing = []
    for std in all_standard_clauses:
        if std.clause_id not in matched_clause_ids:
            missing.append(std)
    return missing
