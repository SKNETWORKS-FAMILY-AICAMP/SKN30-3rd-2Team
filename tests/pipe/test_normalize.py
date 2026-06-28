"""
[작업 규격 · 담당: 팀원 A] pipe.normalize — 마크다운 → 표준조항 정규화 (도메인)

순수 청크 분해는 adapter.splitter 가 담당(이미 구현·테스트됨). 여기서는 "제N조" 해석과
category 라벨링 같은 도메인 판단을 검증합니다.

구현 대상: src/pipe/normalize.py
  - split_markdown_clauses(md_text) -> list[Clause]   # 제N조 청크만 Clause 로
  - label_category(num, title, text) -> Category       # 키워드 → category

👉 구현을 시작하면 pytestmark(skip) 줄을 삭제하고 빨강 → 초록으로 만드세요.
"""
import pytest

from contracts.enums import Category
from contracts.models import Clause

pytestmark = pytest.mark.skip(reason="TDD 규격 — 담당: 팀원 A. 구현 시작 시 이 줄 삭제")

SAMPLE_MD = """\
### <전문>
이 부분은 조항이 아니므로 제외됩니다.

### 제1조(기본원칙)
도급인과 수급인은 신의에 따라 성실히 계약을 이행한다.

### 제20조 (지식재산권의 귀속)
결과물에 대한 지식재산권은 공동소유로 한다.
"""


# --- split_markdown_clauses: 제N조만 Clause 로 (전문 제외) ---
def test_제N조만_Clause로_변환():
    from pipe.normalize import split_markdown_clauses
    clauses = split_markdown_clauses(SAMPLE_MD)
    assert len(clauses) == 2
    assert all(isinstance(c, Clause) for c in clauses)


def test_조번호와_제목_추출():
    from pipe.normalize import split_markdown_clauses
    c1 = split_markdown_clauses(SAMPLE_MD)[0]
    assert c1.num == "제1조"
    assert c1.title == "기본원칙"
    assert "신의에 따라" in c1.text


# --- label_category: 키워드 → Category ---
def test_저작권_조항은_IP_OWNERSHIP():
    from pipe.normalize import label_category
    assert label_category("제20조", "지식재산권의 귀속", "저작권은...") == Category.IP_OWNERSHIP


def test_보수_조항은_PAYMENT():
    from pipe.normalize import label_category
    assert label_category("제6조", "보수", "보수는 금 원으로 한다") == Category.PAYMENT


def test_비밀준수_조항은_CONFIDENTIALITY():
    from pipe.normalize import label_category
    assert label_category("제17조", "비밀준수", "영업비밀을...") == Category.CONFIDENTIALITY
