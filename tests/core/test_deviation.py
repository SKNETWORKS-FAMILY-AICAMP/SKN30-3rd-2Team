"""core 이탈 분류 규격 테스트 — calculate_text_similarity / classify_clause_deviation / detect_missing_clauses.

v1 리뷰(눈금: src/eval/golden/v1_review.md §2 원인 A) 반영 규격:
- 유사도는 조↔조 전체가 아니라 **항↔항 정렬** 후 최적 쌍의 글자 일치율로 잰다.
  (단문 user_clause vs 조 전체 비교로 NONE 도달이 불가능했던 축퇴 해소)
- 일치율이 높아도 **치명 변경(부정어 플립·숫자·당사자 스왑)** 이 있으면 CHANGED 로 강제.
"""
import pytest

from contracts.enums import ContractType, Category, Deviation
from contracts.models import StandardClause
from core import (
    CRITICAL_NEGATION,
    CRITICAL_NUMBER,
    CRITICAL_PARTY,
    calculate_text_similarity,
    classify_clause_deviation,
    detect_critical_changes,
    detect_missing_clauses,
)

# 여러 항(①②③)으로 구성된 거대 표준 조항 — 실코퍼스(03_normalized) 포맷과 동일하게
# 첫 항은 '### 제N조(제목)' 헤더와 같은 줄, 이후 항은 줄 시작.
STD_MULTI = (
    "### 제18조(손해배상) ① 수급인이 업무 수행 과정에서 도급인에게 손해를 발생시킨 경우 그 손해를 배상한다.\n\n"
    "② 도급인은 인도일부터 14일 이내에 검사 결과를 서면으로 통지한다.\n\n"
    "③ 검사 결과 하자가 있는 경우 수급인은 지체 없이 보완한다."
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


def test_단문이_거대조항의_한_항과_동일하면_유사도_1():
    """축퇴 해소 핵심: user 단문 vs 표준 조 전체라도, 항↔항 정렬로 일치가 잡혀야 한다."""
    user = "도급인은 인도일부터 14일 이내에 검사 결과를 서면으로 통지한다."
    assert calculate_text_similarity(user, STD_MULTI) == pytest.approx(1.0)


def test_항_기호_체계가_달라도_동일_내용이면_유사도_1():
    """① vs 1. 같은 번호 체계 차이는 내용 변경이 아니다."""
    user = "1. 도급인은 인도일부터 14일 이내에 검사 결과를 서면으로 통지한다."
    assert calculate_text_similarity(user, STD_MULTI) == pytest.approx(1.0)


def test_조_헤더_포함_여부는_유사도에_영향_없음():
    """'제N조(제목)' 헤더는 정규화로 제거 — 첫 항 비교가 헤더 때문에 깎이면 안 된다."""
    user = "제18조(손해배상) 수급인이 업무 수행 과정에서 도급인에게 손해를 발생시킨 경우 그 손해를 배상한다."
    assert calculate_text_similarity(user, STD_MULTI) == pytest.approx(1.0)


def test_거대조항의_다른_항과는_유사도_낮음():
    user = "수급인은 계약 종료 후 3년간 경쟁사에 대한 용역 제공을 하지 않는다."
    assert calculate_text_similarity(user, STD_MULTI) < 0.85


# --- detect_critical_changes (치명 변경 명시 검출 — 일치율과 독립) ---
def test_부정어_플립_검출():
    user = "제10조에 따라 도급인은 수급인에게 지연 이자를 부과하지 아니한다."
    std = "제10조에 따라 도급인은 수급인에게 지연 이자를 부과한다."
    assert CRITICAL_NEGATION in detect_critical_changes(user, std)


def test_숫자_변경_검출():
    user = "손해배상액은 총 보수의 50%를 한도로 한다."
    std = "손해배상액은 총 보수의 10%를 한도로 한다."
    assert CRITICAL_NUMBER in detect_critical_changes(user, std)


def test_당사자_스왑_검출():
    user = "검사에 소요되는 비용은 을이 부담한다."
    std = "검사에 소요되는 비용은 갑이 부담한다."
    assert CRITICAL_PARTY in detect_critical_changes(user, std)


def test_동일_본문은_치명_변경_없음():
    text = "수급인은 결과물을 도급인에게 인도하며, 대금은 14일 이내에 지급한다."
    assert detect_critical_changes(text, text) == []


def test_목적격_조사_을은_당사자로_오인하지_않음():
    """'결과물을'의 '을'(조사)은 당사자 '을'이 아니다 — 오탐 가드."""
    user = "수급인은 검수된 결과물을 도급인에게 즉시 인도한다."
    std = "수급인은 완성된 결과물을 도급인에게 즉시 인도한다."
    assert CRITICAL_PARTY not in detect_critical_changes(user, std)


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


def test_거대조항의_한_항과_동일한_단문은_NONE():
    """v1 축퇴 재발 방지: 표준(조 전체)과 길이가 달라도 항 단위로 같으면 NONE 이어야 한다."""
    std = _std("a", text=STD_MULTI)
    user = "도급인은 인도일부터 14일 이내에 검사 결과를 서면으로 통지한다."
    assert classify_clause_deviation(user, std, 0.9, match_threshold=0.5) == Deviation.NONE


def test_일치율_높아도_부정어_플립이면_CHANGED():
    std = _std("a", text="제10조에 따라 도급인은 수급인에게 지연 이자를 부과한다.")
    user = "제10조에 따라 도급인은 수급인에게 지연 이자를 부과하지 아니한다."
    assert classify_clause_deviation(user, std, 0.9, match_threshold=0.5) == Deviation.CHANGED


def test_일치율_높아도_숫자_변경이면_CHANGED():
    std = _std("a", text="손해배상액은 총 보수의 10%를 한도로 한다.")
    user = "손해배상액은 총 보수의 50%를 한도로 한다."
    assert classify_clause_deviation(user, std, 0.9, match_threshold=0.5) == Deviation.CHANGED


def test_일치율_높아도_당사자_스왑이면_CHANGED():
    std = _std("a", text="검사에 소요되는 비용은 갑이 부담한다.")
    user = "검사에 소요되는 비용은 을이 부담한다."
    assert classify_clause_deviation(user, std, 0.9, match_threshold=0.5) == Deviation.CHANGED


# --- detect_missing_clauses ---
def test_매칭안된_표준조항은_누락으로():
    all_std = [_std("a"), _std("b"), _std("c")]
    missing = detect_missing_clauses(all_std, matched_clause_ids={"a"})
    assert {m.clause_id for m in missing} == {"b", "c"}
