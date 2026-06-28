"""core 이탈 분류 규격 테스트 — calculate_text_similarity / classify_clause_deviation / detect_missing_clauses."""
from contracts.enums import ContractType, Category, Deviation
from contracts.models import StandardClause
from core import (
    calculate_text_similarity,
    classify_clause_deviation,
    detect_missing_clauses,
)


def _std(clause_id: str, text: str = "표준 조항 본문입니다.") -> StandardClause:
    return StandardClause(
        clause_id=clause_id, contract_type=ContractType.SW_FREELANCE,
        category=Category.PAYMENT, title="t", text=text, source="s", version="2020",
    )


# --- calculate_text_similarity ---
def test_동일_본문은_유사도_1():
    assert calculate_text_similarity("가나다 라마", "가나다라마") == 1.0  # 공백 무시


def test_완전히_다른_본문은_낮은_유사도():
    assert calculate_text_similarity("저작권 귀속", "대금 지급 일정") < 0.5


# --- classify_clause_deviation ---
def test_매칭없으면_EXTRA():
    assert classify_clause_deviation("내 조항", None, 0.0, match_threshold=0.5) == Deviation.EXTRA


def test_점수_미달이면_EXTRA():
    std = _std("a")
    assert classify_clause_deviation("내 조항", std, 0.3, match_threshold=0.5) == Deviation.EXTRA


def test_본문_거의_같으면_NONE():
    std = _std("a", text="동일한 본문")
    assert classify_clause_deviation("동일한 본문", std, 0.9, match_threshold=0.5) == Deviation.NONE


def test_매칭됐지만_본문_차이_크면_CHANGED():
    std = _std("a", text="저작권은 도급인과 수급인의 공동소유로 한다.")
    user = "저작권 일체는 대가 없이 전부 도급인에게 귀속된다."
    assert classify_clause_deviation(user, std, 0.9, match_threshold=0.5) == Deviation.CHANGED


# --- detect_missing_clauses ---
def test_매칭안된_표준조항은_누락으로():
    all_std = [_std("a"), _std("b"), _std("c")]
    missing = detect_missing_clauses(all_std, matched_clause_ids={"a"})
    assert {m.clause_id for m in missing} == {"b", "c"}
