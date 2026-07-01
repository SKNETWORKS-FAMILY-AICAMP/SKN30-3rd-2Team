"""
[작업 규격 · 담당: 팀원 C + 리드] pipe.review_pipe — review_contract 조립

기획서 4.1/4.2 의 동결 출력 계약을 만족하는지 검증합니다. (MCP `review_contract` 본체)
core 의 순수 함수(select_best_match·classify_clause_deviation·detect_missing_clauses·
roll_up_sub_chunks·detect_toxic_patterns)를 조립하고, 외부 작업은 ports 로 **주입**받습니다.

검증 대상:
  1. 반환은 DeviationResult 리스트 (4.1)
  2. 검색 결과가 없으면 NO_MATCH, 후보는 있으나 임계 미달이면 EXTRA (4.2 / core 규격 구분)
  3. 강하게 매칭 + 본문 상이 → CHANGED + grounding 부착, 본문 동일 → NONE + grounding 없음
  4. 어떤 사용자 조항에도 매칭 안 된 표준조항은 MISSING
  5. 독소 패턴 역방향 검색 결과가 toxic_patterns 에 채워짐
  6. 서브청크 roll-up 으로 부모 표준조항이 매칭됨
"""
from typing import Any, Dict, List

from contracts.enums import ContractType, Category, Deviation, ToxicPattern
from contracts.models import Clause, StandardClause, GroundingLaw, DeviationResult
from pipe.review_pipe import review_contract


# --- 표준조항 코퍼스 ---
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

_ART20_HIT = {
    "id": "sw_freelance-art20", "text": ART20.text,
    "contract_type": "SW_FREELANCE", "category": "IP_OWNERSHIP",
    "title": ART20.title, "source": ART20.source, "version": "2020",
    "fusion_score": 0.03,
}
_TOXIC_HIT = {
    "id": "toxic-ip_total_free-01", "text": "저작권 등 일체의 권리를 전부 무상으로 양도한다.",
    "pattern": "IP_TOTAL_FREE", "category": "IP_OWNERSHIP", "title": "IP 전부 무상 귀속",
}


class FakeRetriever:
    """컬렉션·질의별 고정 결과를 반환하는 검색 포트 fake (search_many 로 배치 검색)."""
    def _search_one(self, collection_name: str, query: str) -> List[Dict[str, Any]]:
        if collection_name == "standard_clauses":
            if "저작권" in query or "지식재산" in query:
                return [dict(_ART20_HIT)]
            return []
        if collection_name == "toxic_patterns":
            if "무상" in query:
                return [dict(_TOXIC_HIT)]
            return []
        return []  # standard_sub_chunks 기본 없음

    def search(self, collection_name, query, search_type="hybrid", metadata_filter=None, top_k=5):
        return self._search_one(collection_name, query)

    def search_many(self, collection_name, queries, search_type="hybrid", metadata_filter=None, top_k=5):
        return [self._search_one(collection_name, q) for q in queries]


class FakeSubChunkRetriever(FakeRetriever):
    """standard_clauses 는 비고, standard_sub_chunks 만 art20 부모로 히트."""
    def _search_one(self, collection_name, query):
        if collection_name == "standard_sub_chunks" and ("저작권" in query or "지식재산" in query):
            return [{"id": "sw_freelance-art20-sub01", "text": ART20.text,
                     "parent_clause_id": "sw_freelance-art20", "sub_chunk_index": 0}]
        if collection_name == "standard_clauses":
            return []  # 조항 레벨은 일부러 미스
        return super()._search_one(collection_name, query)


class _Reranker:
    """모든 후보에 고정 로짓을 부여하는 리랭커 fake (logit>0 → sigmoid>0.5 → 매칭)."""
    def __init__(self, logit: float):
        self._logit = logit

    def compute_scores(self, query, documents):
        return [self._logit] * len(documents)

    def rerank(self, query, items, text_key="text", top_k=None):
        out = [{**it, "rerank_score": self._logit} for it in items]
        out.sort(key=lambda x: x["rerank_score"], reverse=True)
        return out[:top_k] if top_k is not None else out


HIGH_RERANKER = _Reranker(8.0)   # sigmoid≈0.9997 → 매칭 인정
LOW_RERANKER = _Reranker(-8.0)   # sigmoid≈0.0003 → 임계 미달


class FakeGrounder:
    def get_grounding(self, _category: Category) -> List[GroundingLaw]:
        return [GroundingLaw(법령명="저작권법", 조번호="제5조", 본문="...", 출처="국가법령정보")]

    def query_law(self, _clause_text: str) -> List[GroundingLaw]:
        return []


def _review(clauses, retriever=None, reranker=HIGH_RERANKER):
    return review_contract(
        clauses, ContractType.SW_FREELANCE,
        retriever=retriever or FakeRetriever(),
        reranker=reranker,
        grounder=FakeGrounder(),
        all_standard_clauses=ALL_STANDARD,
    )


def test_반환은_DeviationResult_리스트():
    results = _review([Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속은 회사에 있다")])
    assert isinstance(results, list)
    assert all(isinstance(r, DeviationResult) for r in results)


def test_검색결과_없으면_NO_MATCH():
    clause = Clause(idx=1, num="제9조", title="기타", text="완전히 무관한 비표준 내용")
    results = _review([clause])
    target = [r for r in results if r.user_clause == clause.text]
    assert target and target[0].deviation == Deviation.NO_MATCH


def test_후보는_있으나_임계미달이면_EXTRA():
    # 검색은 art20 을 반환하지만 리랭커 점수가 낮아 임계 미달 → NO_MATCH 아니라 EXTRA
    clause = Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속은 회사에 있다")
    results = _review([clause], reranker=LOW_RERANKER)
    target = [r for r in results if r.user_clause == clause.text]
    assert target and target[0].deviation == Deviation.EXTRA


def test_강한_매칭_상이본문은_CHANGED_와_근거부착():
    clause = Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속은 회사에 있다")
    results = _review([clause])
    matched = [r for r in results if r.matched_standard and r.matched_standard.clause_id == "sw_freelance-art20"]
    assert matched
    assert matched[0].deviation == Deviation.CHANGED
    assert len(matched[0].grounding) >= 1


def test_본문_동일하면_NONE_이고_근거없음():
    clause = Clause(idx=1, num="제20조", title="지식재산권", text=ART20.text)
    results = _review([clause])
    matched = [r for r in results if r.matched_standard and r.matched_standard.clause_id == "sw_freelance-art20"]
    assert matched and matched[0].deviation == Deviation.NONE
    assert matched[0].grounding == []  # NONE 은 이탈이 아니므로 grounding 미부착


def test_매칭안된_표준조항은_MISSING():
    results = _review([Clause(idx=1, num="제5조", title="저작권", text="저작권 귀속")])
    missing_ids = [
        r.matched_standard.clause_id for r in results
        if r.deviation == Deviation.MISSING and r.matched_standard
    ]
    assert "sw_freelance-art99" in missing_ids


def test_독소패턴_역방향검색이_toxic_patterns에_채워짐():
    clause = Clause(idx=1, num="제5조", title="저작권", text="저작권을 전부 무상으로 양도한다")
    results = _review([clause])
    target = [r for r in results if r.user_clause == clause.text]
    assert target and ToxicPattern.IP_TOTAL_FREE in target[0].toxic_patterns


def test_서브청크_rollup으로_부모조항_매칭():
    # standard_clauses 미스 + standard_sub_chunks 히트 → parent(art20) 로 roll-up 매칭
    clause = Clause(idx=1, num="제20조", title="지식재산권", text=ART20.text)
    results = _review([clause], retriever=FakeSubChunkRetriever())
    matched = [r for r in results if r.matched_standard and r.matched_standard.clause_id == "sw_freelance-art20"]
    assert matched and matched[0].deviation != Deviation.NO_MATCH
