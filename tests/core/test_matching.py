"""core.select_best_match · check_coverage 규격 테스트."""
from contracts.enums import ContractType, Category
from contracts.models import StandardClause
from core import select_best_match, check_coverage


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


# ── check_coverage ────────────────────────────────────────────────────────────

def test_check_coverage_전체_커버():
    """모든 표준 항이 사용자 항과 임계 이상으로 매칭 → fully covered."""
    matrix = [[0.9, 0.1], [0.1, 0.8]]
    covered, uncovered = check_coverage(["id1", "id2"], matrix, threshold=0.5)
    assert covered is True
    assert uncovered == []


def test_check_coverage_미커버_항_탐지():
    """id2 행의 모든 사용자 항 점수가 임계 미만 → id2 미커버."""
    matrix = [[0.9, 0.1], [0.3, 0.2]]
    covered, uncovered = check_coverage(["id1", "id2"], matrix, threshold=0.5)
    assert covered is False
    assert uncovered == ["id2"]


def test_check_coverage_복수_미커버():
    """id1·id3 행이 미커버, id2만 커버."""
    matrix = [[0.1, 0.2], [0.9, 0.1], [0.2, 0.3]]
    covered, uncovered = check_coverage(["id1", "id2", "id3"], matrix, threshold=0.5)
    assert covered is False
    assert set(uncovered) == {"id1", "id3"}


def test_check_coverage_빈_standard_ids():
    """표준 항 목록이 비어 있으면 항상 fully covered."""
    covered, uncovered = check_coverage([], [], threshold=0.5)
    assert covered is True
    assert uncovered == []


def test_check_coverage_임계값_경계_커버_인정():
    """점수가 threshold와 정확히 같으면 커버됨으로 처리."""
    covered, uncovered = check_coverage(["id1"], [[0.5]], threshold=0.5)
    assert covered is True
    assert uncovered == []


def test_check_coverage_사용자_항_없음_미커버():
    """사용자 항이 0개(빈 행)면 해당 표준 항은 미커버."""
    covered, uncovered = check_coverage(["id1"], [[]], threshold=0.5)
    assert covered is False
    assert "id1" in uncovered


def test_check_coverage_미커버_id_순서_보존():
    """uncovered_ids 순서는 standard_ids 입력 순서와 동일."""
    matrix = [[0.1], [0.9], [0.1], [0.9]]
    _, uncovered = check_coverage(["a", "b", "c", "d"], matrix, threshold=0.5)
    assert uncovered == ["a", "c"]
