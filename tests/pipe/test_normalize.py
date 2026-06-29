"""
[작업 규격 · 담당: 팀원 A] pipe.normalize — 마크다운 → 표준조항 정규화 (도메인)

구현 대상: src/pipe/normalize.py
  - split_markdown_clauses(md_text) -> list[Clause]
  - build_category_vectors() -> None   (_category_vectors 전역 초기화)
  - label_category(num, title, text) -> Category
      _embedder / _category_vectors 전역 참조 — 테스트에서 monkeypatch 로 교체
  - normalize_file(md_path, contract_type, version) -> list[StandardClause]
"""
import numpy as np
import pytest

from contracts.enums import Category, ContractType
from contracts.models import Clause

pytestmark = pytest.mark.skip(reason="리뷰 반영 후 skip 삭제")

# ── FakeEmbedder ─────────────────────────────────────────────────────────────

class FakeEmbedder:
    """
    Category.anchors 키워드 포함 여부로 차원별 점수를 부여하는 결정론적 모의 임베더.
    다중어 앵커("보수 지급")를 사용하므로 "하자보수" 같은 복합어에 오탐이 없습니다.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        cats = list(Category)
        vecs = []
        for text in texts:
            vec = [0.0] * len(cats)
            for i, cat in enumerate(cats):
                for anchor in cat.anchors:
                    if anchor in text:
                        vec[i] += 1.0
            norm = sum(x ** 2 for x in vec) ** 0.5
            vecs.append([x / norm for x in vec] if norm > 0 else vec)
        return vecs


# ── 픽스처 ───────────────────────────────────────────────────────────────────

@pytest.fixture
def patch_globals(monkeypatch):
    """
    normalize 모듈의 _embedder / _category_vectors 전역을 FakeEmbedder 로 교체합니다.
    테스트 종료 후 monkeypatch 가 자동으로 원복합니다.
    """
    import pipe.normalize as normalize

    fake_embedder = FakeEmbedder()
    fake_vectors = {
        cat: list(np.mean(fake_embedder.embed_documents(cat.anchors), axis=0))
        for cat in Category
    }

    monkeypatch.setattr(normalize, "_embedder", fake_embedder)
    monkeypatch.setattr(normalize, "_category_vectors", fake_vectors)


# ── SAMPLE 마크다운 ───────────────────────────────────────────────────────────

SAMPLE_MD = """\
### <전문>
이 부분은 조항이 아니므로 제외됩니다.

### 제1조(기본원칙)
도급인과 수급인은 신의에 따라 성실히 계약을 이행한다.

### 제20조 (지식재산권의 귀속)
결과물에 대한 지식재산권은 공동소유로 한다.
"""


# ── split_markdown_clauses ────────────────────────────────────────────────────

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


# ── label_category ────────────────────────────────────────────────────────────

def test_저작권_조항은_IP_OWNERSHIP(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제20조", "지식재산권의 귀속",
        "지식재산권 귀속은 공동소유로 하며 저작권도 동일하게 적용한다.",
    ) == Category.IP_OWNERSHIP


def test_보수_조항은_PAYMENT(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제6조", "보수",
        "도급인은 수급인에게 보수 금액을 지급 시기에 따라 지급한다.",
    ) == Category.PAYMENT


def test_비밀준수_조항은_CONFIDENTIALITY(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제17조", "비밀준수",
        "당사자는 영업비밀을 제3자에게 유출하지 않는다.",
    ) == Category.CONFIDENTIALITY


def test_하자담보_조항은_WARRANTY_PAYMENT_아님(patch_globals):
    """
    회귀 테스트: "하자보수"가 본문에 있어도 PAYMENT 가 아닌 WARRANTY 로 분류되어야 합니다.
    키워드 하드코딩("보수" in text)은 이 테스트를 통과하지 못합니다.
    """
    from pipe.normalize import label_category
    result = label_category(
        "제19조", "하자의 담보",
        "하자담보 기간은 12개월로 하며, 수급인은 하자보수 의무를 진다.",
    )
    assert result == Category.WARRANTY
    assert result != Category.PAYMENT


def test_계약기간_조항은_CONTRACT_PERIOD(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제5조", "계약기간",
        "본 계약의 계약 기간은 업무 착수일부터 근로 개시일까지로 한다.",
    ) == Category.CONTRACT_PERIOD


def test_납품검수_조항은_DELIVERY_INSPECTION(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제11조", "납품",
        "수급인은 납기일까지 계약목적물을 납품하고 도급인은 검수 기준에 따라 검사한다.",
    ) == Category.DELIVERY_INSPECTION


def test_재하도급_조항은_SUBCONTRACTING(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제15조", "재하도급 금지",
        "수급인은 도급인의 서면 승인 없이 재하도급 및 재위탁을 할 수 없다.",
    ) == Category.SUBCONTRACTING


def test_손해배상_조항은_LIABILITY(patch_globals):
    from pipe.normalize import label_category
    assert label_category(
        "제18조", "손해배상",
        "계약 위반으로 손해배상 청구가 발생한 경우 귀책사유 있는 자가 배상 책임을 진다.",
    ) == Category.LIABILITY


def test_미분류_조항은_ValueError(patch_globals):
    """
    어떤 카테고리와도 유사도가 낮은 조항은 ValueError 를 발생시켜야 합니다.
    SCOPE_SOW 묵시적 fallback 금지 (AGENTS.md "조용한 실패 금지").
    """
    from pipe.normalize import label_category
    with pytest.raises(ValueError):
        label_category(
            "제1조", "기본원칙",
            "당사자는 신의성실의 원칙에 따라 본 계약을 이행한다.",
        )


# ── normalize_file ────────────────────────────────────────────────────────────

SMOKE_MD = """\
### 제6조(보수)
도급인은 수급인에게 보수 금액을 지급 시기에 따라 지급한다.

### 제17조(비밀준수)
당사자는 영업비밀을 보호하고 비밀 유지 의무를 진다.
"""


def test_normalize_file_표준조항_리스트_반환(tmp_path, patch_globals):
    from pipe.normalize import normalize_file
    md_file = tmp_path / "test.md"
    md_file.write_text(SMOKE_MD, encoding="utf-8")

    clauses = normalize_file(str(md_file), ContractType.SW_FREELANCE, "2024")

    assert len(clauses) == 2
    assert clauses[0].category == Category.PAYMENT
    assert clauses[1].category == Category.CONFIDENTIALITY


def test_normalize_file_clause_id_형식(tmp_path, patch_globals):
    """clause_id 는 '{contract_type}-art{N}' 형식이어야 합니다."""
    from pipe.normalize import normalize_file
    md_file = tmp_path / "test.md"
    md_file.write_text(SMOKE_MD, encoding="utf-8")

    clauses = normalize_file(str(md_file), ContractType.SW_FREELANCE, "2024")

    assert clauses[0].clause_id == "sw_freelance-art6"
    assert clauses[1].clause_id == "sw_freelance-art17"
