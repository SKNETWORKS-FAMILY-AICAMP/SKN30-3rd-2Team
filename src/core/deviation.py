import difflib
from typing import List, Set, Optional
from contracts.enums import Deviation
from contracts.models import StandardClause

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    두 조항 본문의 내용 일치율(0~1)을 계산합니다.
    select_best_match로 대응 표준조항이 확정된 뒤, 그 내용이 얼마나 바뀌었는지를
    판단하기 위해 classify_clause_deviation 내부에서 호출됩니다.
    공백을 제거하는 이유는 계약서마다 줄바꿈·들여쓰기 형식이 달라도 내용이 같으면
    동일로 처리하기 위해서입니다.
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
    사용자 조항 하나에 대해 select_best_match 결과를 받아 이탈 유형을 확정합니다.
    조항 단위 검토 루프의 마지막 판정 단계로, EXTRA / CHANGED / NONE 세 가지를 반환합니다.

    두 임계치의 역할이 다릅니다.
    - match_threshold: 대응 표준조항이 '존재한다'고 볼 수 있는 최소 유사도.
      미달이면 이 조항은 표준에 없는 조항(EXTRA)으로 간주합니다.
    - change_threshold: 대응은 됐지만 내용이 '충분히 같다'고 볼 수 있는 본문 일치율.
      미달이면 표준 대비 내용이 변경된 조항(CHANGED)으로 분류합니다.

    이 함수가 다루지 않는 케이스:
    - MISSING: 표준조항이 사용자 계약서에서 아예 누락된 경우 → detect_missing_clauses
    - NO_MATCH: 검색 자체가 후보를 반환하지 못한 경우 → pipe 레이어에서 처리
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
    모든 사용자 조항을 처리한 뒤 루프 종료 시점에 한 번 호출됩니다.
    classify_clause_deviation이 "내 조항이 표준의 어디에 해당하는가"를 보는 방향이라면,
    이 함수는 반대 방향으로 "표준의 어느 조항이 내 계약서에 한 번도 등장하지 않았는가"를 찾습니다.
    matched_clause_ids는 루프에서 EXTRA·CHANGED·NONE 판정을 받은 조항들의 clause_id 집합입니다.
    """
    missing = []
    for std in all_standard_clauses:
        if std.clause_id not in matched_clause_ids:
            missing.append(std)
    return missing
