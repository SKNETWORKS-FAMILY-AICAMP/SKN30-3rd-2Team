import difflib
import re
from typing import List, Optional, Set, Tuple

from contracts.enums import Deviation
from contracts.models import StandardClause

from .splitter import split_into_sub_chunks

# ── 치명 변경(critical change) 사유 표식 ─────────────────────────────────────
# 임베딩·글자 일치율이 "거의 같다"고 뭉개는, 법적으로 정반대가 되는 변경을 규칙으로 잡는다.
# (v1 리뷰 §3 — 부정어/숫자/당사자. contracts enum 이 아니라 core 내부 상수: 동결 스키마 불변)
CRITICAL_NEGATION = "negation"  # 부정어 플립: "부과한다" ↔ "부과하지 아니한다"
CRITICAL_NUMBER = "number"      # 숫자 변경: 금액·기간·비율 ("10%" ↔ "50%")
CRITICAL_PARTY = "party"        # 당사자 스왑: "갑이 부담" ↔ "을이 부담"

# '### 제N조(제목)' 형태의 조 헤더 — 실코퍼스(03_normalized)의 첫 항에 붙어 있으며,
# 헤더 유무는 내용 변경이 아니므로 비교 전에 제거한다. (제목 괄호가 없는 '제N조에 따라…'
# 같은 본문 인용은 제거하지 않도록 괄호를 필수로 요구)
_HEADER_RE = re.compile(r"^\s*#{0,6}\s*제\s*\d+\s*조(?:의\s*\d+)?\s*\([^)]*\)\s*")
# 항·호 선두 기호(①~⑳, 숫자+점) — 번호 체계 차이(① vs 1.)는 내용 변경이 아니다.
_SYMBOL_PREFIX_RE = re.compile(r"^\s*(?:[①-⑳]|\d+\.)\s*")

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# 부정 표현: 공백 제거 후 텍스트 기준 ("하지 않"→"하지않", "아니 된다"→"아니된다")
_NEGATION_RE = re.compile(r"아니하|아니한|아니되|않|못한다|못하")
# 당사자 토큰: 역할 명사는 그대로, 한 글자 당사자(갑/을)는 조사·경계 문맥이 있을 때만
# 인정한다 — '결과물을'의 목적격 조사 '을', '갑작스러운'의 '갑' 오탐 방지.
_PARTY_RE = re.compile(
    r"수급사업자|원사업자|도급인|수급인|위탁자|수탁자|발주자"
    r"|(?<![가-힣])[갑을](?=[은이가의와과에]|[^가-힣]|$)"
)


def _strip_prefix(text: str) -> str:
    """조 헤더와 항·호 선두 기호를 제거합니다 (서식 차이를 비교에서 배제)."""
    return _SYMBOL_PREFIX_RE.sub("", _HEADER_RE.sub("", text))


def _normalize(text: str) -> str:
    """비교용 정규화: 헤더·기호 제거 후 모든 공백 제거 (줄바꿈·들여쓰기 무시)."""
    return "".join(_strip_prefix(text).split())


def _align_sub_chunks(user_text: str, standard_text: str) -> List[Tuple[str, str, float]]:
    """사용자 항마다 가장 닮은 표준 항을 짝지어 (사용자 항, 표준 항, 일치율) 목록을 만듭니다.

    v1 축퇴(리뷰 §2 원인 A)의 근본 수정: 단문 사용자 조항을 표준 '조 전체'와 통째로 비교하면
    SequenceMatcher.ratio 의 상한이 2·min(길이)/(길이 합)으로 묶여 내용이 같아도 임계값에
    도달할 수 없다. 그래서 양쪽을 항·호 단위로 쪼갠 뒤 문장↔문장 스케일에서 비교한다.
    반환되는 항 텍스트는 헤더·기호 제거만 된 원형(공백 유지) — 당사자 검출이 어절 경계를
    쓰므로 공백을 남긴다.
    """
    user_subs = [s for s in (_strip_prefix(c) for c in split_into_sub_chunks(user_text)) if s.strip()]
    std_subs = [s for s in (_strip_prefix(c) for c in split_into_sub_chunks(standard_text)) if s.strip()]
    if not user_subs or not std_subs:
        return []

    std_norms = [_normalize(s) for s in std_subs]
    pairs: List[Tuple[str, str, float]] = []
    for u in user_subs:
        u_norm = _normalize(u)
        ratios = [difflib.SequenceMatcher(None, u_norm, s_norm).ratio() for s_norm in std_norms]
        best = max(range(len(ratios)), key=lambda j: ratios[j])
        pairs.append((u, std_subs[best], ratios[best]))
    return pairs


def calculate_text_similarity(text1: str, text2: str) -> float:
    """두 조항 본문의 내용 일치율(0~1)을 계산합니다.

    select_best_match로 대응 표준조항이 확정된 뒤, 그 내용이 얼마나 바뀌었는지를
    판단하기 위해 classify_clause_deviation 내부에서 호출됩니다.
    조↔조 통비교가 아니라 **항↔항 정렬 후 최적 쌍 일치율의 길이 가중 평균**입니다 —
    사용자 조항(단문)과 표준 조항(조 전체)의 길이 차이가 점수를 왜곡하지 않게 하기 위함.
    헤더('제N조(제목)')·항 기호(① vs 1.)·공백은 서식이므로 비교에서 배제합니다.
    """
    pairs = _align_sub_chunks(text1, text2)
    if not pairs:
        # 정규화 후 양쪽 다 빈 텍스트면 동일, 한쪽만 비었으면 불일치
        return 1.0 if _normalize(text1) == _normalize(text2) else 0.0

    weights = [len(_normalize(u)) for u, _, _ in pairs]
    total = sum(weights)
    if total == 0:
        return 0.0
    return sum(r * w for (_, _, r), w in zip(pairs, weights)) / total


def detect_critical_changes(
    user_text: str,
    standard_text: str,
    min_pair_ratio: float = 0.5,
) -> List[str]:
    """일치율로는 안 잡히는 '법적으로 치명적인' 변경을 규칙으로 검출합니다.

    항↔항 정렬로 짝지어진 쌍(정렬이 유의미한 min_pair_ratio 이상만)에 대해:
    - CRITICAL_NEGATION: 부정어 유무가 한쪽에만 있음 ("부과한다" ↔ "부과하지 아니한다")
    - CRITICAL_NUMBER: 숫자 집합이 다름 ("10%" ↔ "50%", "1년" ↔ "5년")
    - CRITICAL_PARTY: 당사자 등장 순서가 다름 ("갑이 부담" ↔ "을이 부담")

    반환은 발견 순서의 중복 없는 사유 목록. 빈 목록이면 치명 변경 없음.
    classify_clause_deviation 이 NONE 판정 직전의 마지막 게이트로 사용합니다.
    """
    reasons: List[str] = []
    for user_sub, std_sub, ratio in _align_sub_chunks(user_text, standard_text):
        if ratio < min_pair_ratio:
            continue  # 정렬이 무의미한 쌍 — 어차피 일치율 게이트에서 CHANGED 처리됨
        u_norm, s_norm = _normalize(user_sub), _normalize(std_sub)

        if bool(_NEGATION_RE.search(u_norm)) != bool(_NEGATION_RE.search(s_norm)):
            if CRITICAL_NEGATION not in reasons:
                reasons.append(CRITICAL_NEGATION)

        if sorted(_NUMBER_RE.findall(u_norm.replace(",", ""))) != sorted(
            _NUMBER_RE.findall(s_norm.replace(",", ""))
        ):
            if CRITICAL_NUMBER not in reasons:
                reasons.append(CRITICAL_NUMBER)

        # 당사자는 순서까지 비교 ("갑이 을에게" ↔ "을이 갑에게" 스왑 포착) — 공백 유지 원형 사용
        if _PARTY_RE.findall(user_sub) != _PARTY_RE.findall(std_sub):
            if CRITICAL_PARTY not in reasons:
                reasons.append(CRITICAL_PARTY)
    return reasons


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
    - change_threshold: 대응은 됐지만 내용이 '충분히 같다'고 볼 수 있는 본문 일치율
      (항↔항 정렬 기준). 미달이면 표준 대비 내용이 변경된 조항(CHANGED)으로 분류합니다.

    NONE 은 두 게이트를 모두 통과해야 합니다: 일치율 ≥ change_threshold 이고,
    치명 변경(부정어 플립·숫자·당사자 스왑, detect_critical_changes)이 없어야 합니다.
    NONE 의 정의는 엄격안 — 서식(헤더·항 기호·공백)만 다르면 NONE, 문구가 바뀌면 CHANGED.

    이 함수가 다루지 않는 케이스:
    - MISSING: 표준조항이 사용자 계약서에서 아예 누락된 경우 → detect_missing_clauses
    - NO_MATCH: 검색 자체가 후보를 반환하지 못한 경우 → pipe 레이어에서 처리
    """
    if matched_standard is None or score < match_threshold:
        return Deviation.EXTRA

    # 본문 텍스트 일치율 비교 (항↔항 정렬)
    similarity = calculate_text_similarity(user_text, matched_standard.text)
    if similarity < change_threshold:
        return Deviation.CHANGED

    # 일치율이 높아도 부정어·숫자·당사자 변경이면 NONE 을 허용하지 않는다
    if detect_critical_changes(user_text, matched_standard.text):
        return Deviation.CHANGED

    return Deviation.NONE

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
