"""
[작업 규격 · 담당: 팀원 C + 리드] pipe.review_pipe — review_contract 조립

기획서 4.1/4.2 의 동결 출력 계약을 만족하는지 검증합니다. (MCP `review_contract` 본체)
core 의 순수 함수(select_best_match·classify_clause_deviation·detect_missing_clauses)를
조립하고, 외부 작업은 ports(Retriever·Grounder)로 **주입**받습니다 → 테스트에서 fake 주입.

구현 대상: src/pipe/review_pipe.py
    review_contract(
        clauses: list[Clause],
        contract_type: ContractType,
        *,
        retriever: Retriever, grounder: Grounder,
        all_standard_clauses: list[StandardClause],
        match_threshold: float = 0.5,
    ) -> list[DeviationResult]

⚠ 이 시그니처는 동결 MCP 계약(4장)에 가깝습니다. 바꾸려면 PM/리드와 먼저 합의하세요.

보장해야 할 것:
  1. 반환은 DeviationResult 리스트 (4.1)
  2. 검색 결과가 없으면 그 조항은 deviation=NO_MATCH (4.2 빈 응답 금지)
  3. 강하게 매칭되면 matched_standard 채워지고 grounding 부착
  4. 어떤 사용자 조항에도 매칭 안 된 표준조항은 MISSING 으로 포함 (3.2)

👉 구현을 시작하면 pytestmark(skip) 줄을 삭제하세요.
"""
import pytest

from typing import List, Dict, Any, Optional
from contracts.enums import ContractType, Category, Deviation
from contracts.models import Clause, StandardClause, GroundingLaw
from adapter.port import Retriever
from contracts.ports import Grounder

pytestmark = pytest.mark.skip(reason="TDD 규격 — 담당: 팀원 C/리드. 구현 시작 시 이 줄 삭제")


# --- 표준조항 코퍼스 (전체) ---
ART20 = StandardClause(
    clause_id="sw_freelance-art20", contract_type=ContractType.SW_FREELANCE,
    category=Category.IP_OWNERSHIP, title="지식재산권의 귀속",
    text="결과물에 대한 지식재산권은 수급인과 도급인의 공동소유로 한다.",
    source="s/제20조", version="2020",
)
ART99_UNMATCHED = StandardClause(
    clause_id="sw_freelance-art99", contract_type=ContractType.SW_FREELANCE,
    category=Category.DISPUTE, title="관할법원", text="분쟁은 관할 법원에서 해결한다.",
    source="s/제99조", version="2020",
)
ALL_STANDARD = [ART20, ART99_UNMATCHED]


class FakeRetriever(Retriever):
    """'저작권' 질의에는 art20 을 강하게 반환, 그 외에는 빈 결과(→ NO_MATCH)."""
    def search(
        self, _collection_name: str, query: str, _search_type: str = "hybrid", _metadata_filter: Optional[Dict[str, Any]] = None, _top_k: int = 5
    ) -> List[Dict[str, Any]]:
        if "저작권" in query or "지식재산" in query:
            return [{
                "id": "sw_freelance-art20", "text": ART20.text,
                "contract_type": "SW_FREELANCE", "category": "IP_OWNERSHIP",
                "title": ART20.title, "source": ART20.source, "version": "2020",
                "score": 0.95, "rerank_score": 0.95, "fusion_score": 0.95,
            }]
        return []


class FakeGrounder(Grounder):
    def get_grounding(self, _category: Category) -> List[GroundingLaw]:
        return [GroundingLaw(법령명="저작권법", 조번호="제5조", 본문="...", 출처="국가법령정보")]

    def query_law(self, _clause_text: str) -> List[GroundingLaw]:
        return []


def _review(clauses):
    from pipe.review_pipe import review_contract
    return review_contract(
        clauses, ContractType.SW_FREELANCE,
        retriever=FakeRetriever(), grounder=FakeGrounder(),
        all_standard_clauses=ALL_STANDARD,
    )


def test_반환은_DeviationResult_리스트():
    from contracts.models import DeviationResult
    results = _review([Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속은 회사에 있다")])
    assert isinstance(results, list)
    assert all(isinstance(r, DeviationResult) for r in results)


def test_검색결과_없으면_NO_MATCH():
    clause = Clause(idx=1, num="제9조", title="기타", text="완전히 무관한 비표준 내용")
    results = _review([clause])
    target = [r for r in results if r.user_clause == clause.text]
    assert target and target[0].deviation == Deviation.NO_MATCH


def test_강한_매칭은_표준조항과_근거_부착():
    clause = Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속은 회사에 있다")
    results = _review([clause])
    matched = [r for r in results if r.matched_standard and r.matched_standard.clause_id == "sw_freelance-art20"]
    assert matched
    assert matched[0].deviation != Deviation.NO_MATCH
    assert len(matched[0].grounding) >= 1  # 법령 근거 부착


def test_매칭안된_표준조항은_MISSING():
    # art20 만 매칭되는 조항 1개 → art99 는 어디에도 안 잡혀 MISSING 이어야 함
    results = _review([Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속")])
    missing_ids = [
        r.matched_standard.clause_id for r in results
        if r.deviation == Deviation.MISSING and r.matched_standard
    ]
    assert "sw_freelance-art99" in missing_ids
