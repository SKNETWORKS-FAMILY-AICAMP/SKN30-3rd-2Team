"""adapter.splitter (MarkdownSplitter) 회귀 테스트 — 순수 마크다운 청크 분해 (도메인 무관)."""
from adapter.markdown_splitter import splitter

SAMPLE_MD = """\
### <전문>
이 부분도 하나의 청크입니다.

### 제1조(기본원칙)
도급인과 수급인은 신의에 따라 성실히 계약을 이행한다.

### 제20조 (지식재산권의 귀속)
결과물에 대한 지식재산권은 공동소유로 한다.
"""


def test_헤더_단위로_청크_분해():
    chunks = splitter.split(SAMPLE_MD)
    assert len(chunks) == 3  # 전문 포함 모든 섹션 (도메인 필터링은 normalize 책임)
    assert all(isinstance(c, str) for c in chunks)


def test_각_청크는_자기_헤더를_포함():
    chunks = splitter.split(SAMPLE_MD)
    assert any("제1조" in c and "신의에 따라" in c for c in chunks)


def test_빈_입력은_빈_리스트():
    assert splitter.split("") == []
