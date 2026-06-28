"""core.select_best_match 규격 테스트 — 최고 점수 후보 선택 + 임계치 게이트."""
from contracts.enums import ContractType, Category
from contracts.models import StandardClause
from core import select_best_match


def _std(clause_id: str) -> StandardClause:
    """테스트용 표준조항 생성 헬퍼."""
    return StandardClause(
        clause_id=clause_id, contract_type=ContractType.SW_FREELANCE,
        category=Category.IP_OWNERSHIP, title="t", text="본문",
        source="src", version="2020",
    )


def test_빈_후보는_매칭없음():
    assert select_best_match([], threshold=0.5) == (None, 0.0)


def test_최고점수_후보를_선택():
    a, b = _std("a"), _std("b")
    best, score = select_best_match([(a, 0.3), (b, 0.9)], threshold=0.5)
    assert best.clause_id == "b"
    assert score == 0.9


def test_임계치_미만이면_매칭없음():
    a = _std("a")
    best, score = select_best_match([(a, 0.4)], threshold=0.5)
    assert best is None
    assert score == 0.0


def test_임계치_경계값은_매칭_인정():
    a = _std("a")
    best, score = select_best_match([(a, 0.5)], threshold=0.5)
    assert best.clause_id == "a"
    assert score == 0.5
