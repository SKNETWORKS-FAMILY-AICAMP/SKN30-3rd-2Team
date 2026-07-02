"""KordocParser 조항 분해 규격 테스트.

핵심 불변식: 조항 경계는 마크다운 헤더(#) 유무에 의존하지 않는다. 실제 계약서(DOCX/PDF)는
kordoc 변환 시 "제N조"가 평문 문단으로 나오는 경우가 많아(헤더 없음), 헤더 기반 분해로는
0건 축퇴가 발생했다(트랙 B 실측으로 발견). 순수 함수 `_segment_by_article` 를 직접 검증한다
(kordoc CLI 왕복 없이).
"""
from contracts.implement import KordocParser

parser = KordocParser()


def test_header_less_articles_segmented():
    """# 헤더 없이 평문으로 나온 '제N조' 도 조항으로 분해된다 (핵심 회귀 방지)."""
    md = (
        "프리랜서 계약서\n\n"
        "제1조 (계약의 목적) 본 계약은 용역업무를 의뢰함에 있어…\n\n"
        "제2조 (계약의 범위) 을은 다음 각 호의 작업을 수행한다.\n"
        "1. 항목\n2. 항목\n\n"
        "제3조(손해배상) 을은 손해를 배상할 책임이 있다.\n"
    )
    clauses = parser._segment_by_article(md)
    assert [c.num for c in clauses] == ["제1조", "제2조", "제3조"]
    assert [c.title for c in clauses] == ["계약의 목적", "계약의 범위", "손해배상"]
    # 제2조 본문은 다음 조항 직전까지(각 호 포함) 누적된다.
    assert "1. 항목" in clauses[1].text and "2. 항목" in clauses[1].text


def test_markdown_headed_articles_still_work():
    """기존 헤더(##) 방식 마크다운도 그대로 분해된다 (회귀 방지)."""
    md = "# 계약서\n## 제1조 (목적) 본문 A\n부가 A\n## 제2조(범위)\n본문 B\n"
    clauses = parser._segment_by_article(md)
    assert [(c.num, c.title) for c in clauses] == [("제1조", "목적"), ("제2조", "범위")]


def test_preamble_before_first_article_dropped():
    """첫 '제N조' 이전의 전문/개요는 조항이 아니므로 버린다."""
    md = "표준계약서\n체결 개요 문단\n\n제1조 (목적) 본문\n"
    clauses = parser._segment_by_article(md)
    assert len(clauses) == 1 and clauses[0].num == "제1조"
    assert "체결 개요" not in clauses[0].text


def test_spacing_variants_normalized():
    """'제 12 조' 처럼 공백이 낀 표기도 '제12조' 로 정규화된다."""
    md = "제 12 조 (소송관할) 관할법원은 서울중앙지방법원으로 한다.\n"
    clauses = parser._segment_by_article(md)
    assert clauses[0].num == "제12조"


def test_mid_body_article_reference_not_split():
    """본문 중간(라인 시작 아님)의 '제3조' 언급으로는 분할되지 않는다."""
    md = "제1조 (해지) 전 제3조의 규정에 따라 계약을 해지할 수 있다.\n제2조 (효력) 본문\n"
    clauses = parser._segment_by_article(md)
    assert [c.num for c in clauses] == ["제1조", "제2조"]


def test_no_article_returns_empty():
    """'제N조' 가 전혀 없으면 빈 리스트를 반환한다 (빈 응답이 아니라 명시적 0건)."""
    assert parser._segment_by_article("아무 조항도 없는 일반 문서\n둘째 줄\n") == []
