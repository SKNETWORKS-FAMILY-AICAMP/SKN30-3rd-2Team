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
from contracts.models import Clause, StandardClause, StandardSubChunk, GroundingLaw, DeviationResult
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

    def compute_scores_many(self, queries, docs_per_query):
        # 실제 어댑터와 동일하게 질의별 compute_scores 를 순서대로 위임 (서브클래스 오버라이드 존중)
        return [self.compute_scores(q, docs) for q, docs in zip(queries, docs_per_query)]

    def rerank(self, query, items, text_key="text", top_k=None):
        out = [{**it, "rerank_score": self._logit} for it in items]
        out.sort(key=lambda x: x["rerank_score"], reverse=True)
        return out[:top_k] if top_k is not None else out

    def rerank_many(self, queries, items_per_query, text_key="text", top_k=None):
        return [
            self.rerank(q, items, text_key=text_key, top_k=top_k)
            for q, items in zip(queries, items_per_query)
        ]


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


# ── 커버리지 체크 통합 테스트 ──────────────────────────────────────────────────
#
# 시나리오: 항이 3개(①②③)인 거대 조항(ART58)에서 ②(이자 항)가 사용자 조항에 없음.
# 본문 유사도 기준으로는 NONE 판정되지만, 커버리지 체크가 미커버를 잡아 CHANGED 로 상향.

ART58 = StandardClause(
    clause_id="sw_freelance-art58", contract_type=ContractType.SW_FREELANCE,
    category=Category.PAYMENT, title="하도급대금 지급",
    text="① 원사업자는 대금을 지급한다.\n② 지연 시 이자를 부과한다.\n③ 기한은 60일이다.",
    source="s/제58조", version="2020",
)
_SUB_00 = StandardSubChunk(
    sub_chunk_id="sw_freelance-art58-sub00", parent_clause_id="sw_freelance-art58",
    sub_chunk_index=0, text="① 원사업자는 대금을 지급한다.",
    contract_type=ContractType.SW_FREELANCE,
)
_SUB_01 = StandardSubChunk(
    sub_chunk_id="sw_freelance-art58-sub01", parent_clause_id="sw_freelance-art58",
    sub_chunk_index=1, text="② 지연 시 이자를 부과한다.",
    contract_type=ContractType.SW_FREELANCE,
)
_SUB_02 = StandardSubChunk(
    sub_chunk_id="sw_freelance-art58-sub02", parent_clause_id="sw_freelance-art58",
    sub_chunk_index=2, text="③ 기한은 60일이다.",
    contract_type=ContractType.SW_FREELANCE,
)
_ART58_HIT = {
    "id": "sw_freelance-art58", "text": ART58.text,
    "contract_type": "SW_FREELANCE", "category": "PAYMENT",
    "title": ART58.title, "source": ART58.source, "version": "2020",
    "fusion_score": 0.03,
}
_ART58_SUB_MAP = {"sw_freelance-art58": [_SUB_00, _SUB_01, _SUB_02]}
_ALL_STD_WITH_58 = [ART20, ART58, ART99_UNMATCHED]


class _Art58Retriever(FakeRetriever):
    """standard_clauses 쿼리에 항상 ART58 을 반환하는 검색 fake."""
    def _search_one(self, collection_name, query):
        if collection_name == "standard_clauses":
            return [dict(_ART58_HIT)]
        return []


class _PartialCoverageReranker(_Reranker):
    """rerank 는 고점수, compute_scores 는 '이자' 항(SUB_01) 쿼리만 저점수.

    커버리지 체크 시 SUB_01 이 미커버로 판정되도록 시뮬레이션합니다.
    나머지 항(SUB_00·SUB_02)과 일반 rerank 는 HIGH_RERANKER 와 동일하게 동작합니다.
    """
    def __init__(self):
        super().__init__(8.0)

    def compute_scores(self, query: str, documents: list) -> list:
        # SUB_01.text("② 지연 시 이자를 부과한다.") 가 쿼리일 때 저점수
        if "이자" in query:
            return [-8.0] * len(documents)
        return [8.0] * len(documents)


def _review58(clauses, *, sub_map=_ART58_SUB_MAP, reranker=None, use_coverage=True):
    return review_contract(
        clauses, ContractType.SW_FREELANCE,
        retriever=_Art58Retriever(),
        reranker=reranker or _PartialCoverageReranker(),
        grounder=FakeGrounder(),
        all_standard_clauses=_ALL_STD_WITH_58,
        all_standard_sub_chunks=sub_map,
        coverage_threshold=0.5,
        use_coverage=use_coverage,
    )


def test_서브청크_미커버_NONE에서_CHANGED_상향():
    """표준 서브청크 1개 미커버 → NONE 판정 조항이 CHANGED 로 상향됨."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause])
    target = next(r for r in results if r.user_clause == clause.text)
    assert target.deviation == Deviation.CHANGED


def test_서브청크_미커버_uncovered_ids_채워짐():
    """CHANGED 상향 시 미커버된 표준 항 id 가 uncovered_sub_chunk_ids 에 포함됨."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause])
    target = next(r for r in results if r.user_clause == clause.text)
    assert "sw_freelance-art58-sub01" in target.uncovered_sub_chunk_ids


def test_서브청크_미커버_grounding_부착():
    """CHANGED 상향 시 법령 근거가 grounding 에 부착됨."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause])
    target = next(r for r in results if r.user_clause == clause.text)
    assert len(target.grounding) >= 1


def test_서브청크_전체_커버_NONE_유지():
    """모든 표준 서브청크가 커버됨 → NONE 유지, uncovered_ids 비어있음."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause], reranker=HIGH_RERANKER)
    target = next(r for r in results if r.user_clause == clause.text)
    assert target.deviation == Deviation.NONE
    assert target.uncovered_sub_chunk_ids == []


def test_use_coverage_false_NONE_유지():
    """use_coverage=False 이면 커버리지 체크 전체 스킵 → NONE 유지 (ablation)."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause], use_coverage=False)
    target = next(r for r in results if r.user_clause == clause.text)
    assert target.deviation == Deviation.NONE
    assert target.uncovered_sub_chunk_ids == []


def test_서브청크_맵_미주입_NONE_유지():
    """all_standard_sub_chunks=None 이면 커버리지 체크 없이 NONE 유지."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause], sub_map=None)
    target = next(r for r in results if r.user_clause == clause.text)
    assert target.deviation == Deviation.NONE


def test_서브청크_1개_조항_체크_스킵():
    """std_subs < 2 이면 단순 조항으로 간주해 커버리지 체크 스킵 → NONE 유지."""
    clause = Clause(idx=1, num="제58조", title="하도급대금", text=ART58.text)
    results = _review58([clause], sub_map={"sw_freelance-art58": [_SUB_00]})
    target = next(r for r in results if r.user_clause == clause.text)
    assert target.deviation == Deviation.NONE
