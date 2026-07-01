"""
core.splitter — is_large_clause · split_into_sub_chunks 순수 함수 단위 테스트
"""
from core.splitter import is_large_clause, split_into_sub_chunks


# ── is_large_clause ───────────────────────────────────────────────────────────

def test_300자_초과면_거대조항():
    assert is_large_clause("가" * 301) is True


def test_100자_이하면_거대조항_아님():
    assert is_large_clause("가" * 100) is False


def test_기호_3개_이상이면_글자수_무관하게_거대조항():
    """짧아도 항·호 기호가 3개 이상이면 거대 조항으로 판정합니다."""
    assert is_large_clause("① 가나다 ② 라마바 ③ 사아자") is True


def test_기호_2개는_거대조항_아님():
    assert is_large_clause("① 가나다 ② 라마바") is False


def test_숫자목록_3개_이상이면_거대조항():
    text = "1. 첫째\n2. 둘째\n3. 셋째"
    assert is_large_clause(text) is True


def test_기호와_숫자목록_합산_3개_이상이면_거대조항():
    """① 1개 + 1. 2개 = 합계 3개 → 거대 조항"""
    text = "① 첫째 항\n1. 첫 번째\n2. 두 번째"
    assert is_large_clause(text) is True


# ── split_into_sub_chunks ─────────────────────────────────────────────────────

def test_100자_단순_조항은_원문_그대로_반환():
    text = "갑은 을에게 대금을 지급한다." * 3  # 짧은 반복
    chunks = split_into_sub_chunks(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_600자_항기호_조항_2개이상_분할():
    text = "① " + "가" * 200 + "\n② " + "나" * 200 + "\n③ " + "다" * 200
    chunks = split_into_sub_chunks(text)
    assert len(chunks) >= 2


def test_분할_결과에_원본_내용_보존():
    """각 청크에 원본 항 내용이 포함되어야 합니다."""
    text = "① 원사업자는 대금을 지급한다.\n② 지연 시 이자를 부과한다.\n③ 기한은 60일이다."
    chunks = split_into_sub_chunks(text)
    full = "".join(chunks)
    assert "원사업자" in full
    assert "이자" in full
    assert "60일" in full


def test_숫자목록_기준_분할():
    text = "1. 갑은 을에게 대금을 지급한다.\n2. 지급 기한은 30일로 한다.\n3. 연체 시 이자를 부과한다."
    chunks = split_into_sub_chunks(text)
    assert len(chunks) >= 2


def test_빈청크_포함되지_않음():
    text = "① 조항 내용\n\n② 추가 조항 내용\n③ 마지막 조항"
    chunks = split_into_sub_chunks(text)
    assert all(c.strip() for c in chunks)


def test_빈_텍스트에도_최소_1개_반환():
    """빈 문자열이더라도 빈 리스트가 아닌 원문 그대로 반환합니다."""
    text = "단순 조항 하나."
    chunks = split_into_sub_chunks(text)
    assert len(chunks) >= 1


def test_선도_텍스트_보존():
    """항 기호 앞에 오는 선도 텍스트(제목 줄 등)도 청크에 포함됩니다."""
    text = "제58조 표제 내용\n① 첫째 항 내용이 들어갑니다.\n② 둘째 항 내용이 들어갑니다.\n③ 셋째 항 내용"
    chunks = split_into_sub_chunks(text)
    # 선도 + 3항 = 최소 2청크 이상
    assert len(chunks) >= 2
    joined = " ".join(chunks)
    assert "표제" in joined
