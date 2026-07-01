"""
[담당: 팀원 C + 리드] review_contract — 계약서 전체 검토 조립 (MCP 본체)

규격(통과해야 할 테스트): tests/pipe/test_review_pipe.py
참고 문서: src/pipe/README.md, src/core/README.md, 기획서 4·7장

core 의 순수 함수를 조립하고, 외부 작업(검색·재정렬·법령·그래프)은 ports 로 주입받습니다.
⚠ 시그니처는 동결 MCP 계약(4장)에 가깝습니다 — 변경 시 PM/리드와 먼저 합의하세요.

흐름(기획서 7장):
  batch 검색(Retriever.search_many) → 재정렬(Reranker) → sigmoid 정규화 → select_best_match
  → classify_clause_deviation → grounding(Grounder) → 독소(Toxic)·연관위험(Graph) 풍부화
"""
from typing import Any, Dict, List, Optional, Tuple

from contracts.enums import Category, ContractType, Deviation, ToxicPattern
from contracts.models import Clause, StandardClause, DeviationResult, GroundingLaw
from contracts.ports import Grounder, Graph
from adapter.port import Retriever, Reranker
from core import (
    classify_clause_deviation,
    detect_missing_clauses,
    detect_toxic_patterns,
    roll_up_sub_chunks,
    select_best_match,
    sigmoid,
)

# Chroma 컬렉션 이름 (build_index.py 와 일치)
STANDARD_COLLECTION = "standard_clauses"
SUB_CHUNK_COLLECTION = "standard_sub_chunks"
TOXIC_COLLECTION = "toxic_patterns"


def _normalized_score(hit: Dict[str, Any]) -> float:
    """재정렬을 거친 검색 결과의 rerank_score(로짓)를 0~1 로 정규화합니다.

    search()가 반환하는 fusion_score(RRF, 최댓값 ≈0.033)는 match_threshold(0.5)와 스케일이
    맞지 않으므로 매칭 판정에 쓰지 않습니다. 반드시 Reranker 를 통과한 rerank_score 만 사용합니다.
    """
    return sigmoid(float(hit["rerank_score"])) if "rerank_score" in hit else 0.0


def _standard_from_hit(
    hit: Dict[str, Any],
    standards_by_id: Dict[str, StandardClause],
    contract_type: ContractType,
) -> Optional[StandardClause]:
    """standard_clauses 검색 결과 dict를 StandardClause로 변환합니다."""
    clause_id = hit.get("id") or hit.get("clause_id")
    if not clause_id:
        return None
    if clause_id in standards_by_id:
        return standards_by_id[clause_id]

    # 메모리 코퍼스에 없으면(예: 인덱스와 코퍼스 버전 불일치) 메타데이터로 복원 시도
    if "category" not in hit:
        return None
    return StandardClause(
        clause_id=clause_id,
        contract_type=ContractType(hit.get("contract_type", contract_type.value)),
        category=Category(hit["category"]),
        title=hit.get("title", ""),
        text=hit.get("text", ""),
        source=hit.get("source", ""),
        version=hit.get("version", ""),
    )


def _clause_candidates(
    reranked_hits: List[Dict[str, Any]],
    standards_by_id: Dict[str, StandardClause],
    contract_type: ContractType,
) -> List[Tuple[StandardClause, float]]:
    """standard_clauses 재정렬 결과를 (StandardClause, 정규화 점수) 후보로 변환합니다."""
    candidates: List[Tuple[StandardClause, float]] = []
    for hit in reranked_hits:
        standard = _standard_from_hit(hit, standards_by_id, contract_type)
        if standard is not None:
            candidates.append((standard, _normalized_score(hit)))
    return candidates


def _sub_chunk_candidate(
    reranked_sub_hits: List[Dict[str, Any]],
    standards_by_id: Dict[str, StandardClause],
) -> Optional[Tuple[StandardClause, float]]:
    """서브청크 검색 결과를 parent_clause_id 기준으로 roll-up 해 부모 조항 후보 1개로 만듭니다.

    거대 조항(항·호가 많은 조항)은 조항 전체 임베딩보다 항 단위 서브청크가 더 잘 매칭됩니다.
    parent_clause_id 별 Max Score(core.roll_up_sub_chunks)로 최적 부모를 고른 뒤,
    현재 계약 유형의 표준조항 코퍼스에 존재하는 부모만 후보로 채택합니다.
    (서브청크 인덱스에 저장된 contract_type 메타데이터 필터링을 통해 1차적으로 대상 유형이 좁혀집니다.)
    """
    scored_parents: List[Tuple[str, float]] = [
        (hit["parent_clause_id"], _normalized_score(hit))
        for hit in reranked_sub_hits
        if hit.get("parent_clause_id")
    ]
    parent_id, score = roll_up_sub_chunks(scored_parents)
    if parent_id is None or parent_id not in standards_by_id:
        return None
    return standards_by_id[parent_id], score


def _toxic_from_hits(
    reranked_toxic_hits: List[Dict[str, Any]],
    threshold: float,
) -> List[ToxicPattern]:
    """toxic_patterns 검색 결과를 (ToxicPattern, 점수)로 변환 후 임계 필터링합니다."""
    matches: List[Tuple[ToxicPattern, float]] = []
    for hit in reranked_toxic_hits:
        raw = hit.get("pattern")
        if raw is None:
            continue
        try:
            pattern = ToxicPattern(raw)
        except ValueError:
            continue  # 알 수 없는 패턴 값은 건너뜀 (1차: skip, 후속 로깅 대상)
        matches.append((pattern, _normalized_score(hit)))
    return detect_toxic_patterns(matches, threshold)


def _grounding_for(grounder: Grounder, category: Category) -> List[GroundingLaw]:
    """이탈(CHANGED/MISSING) 조항에만 법령 근거를 부착합니다. GENERAL 은 grounding 대상 아님."""
    if category == Category.GENERAL:
        return []
    return grounder.get_grounding(category)


def review_contract(
    clauses: List[Clause],
    contract_type: ContractType,
    *,
    retriever: Retriever,
    reranker: Reranker,
    grounder: Grounder,
    all_standard_clauses: List[StandardClause],
    graph: Optional[Graph] = None,
    match_threshold: float = 0.5,
    change_threshold: float = 0.85,
    toxic_threshold: float = 0.5,
    top_k: int = 5,
    use_sub_chunk: bool = True,
    use_toxic: bool = True,
) -> List[DeviationResult]:
    """
    사용자 조항들을 표준조항과 비교해 이탈을 탐지하고, 법령 근거·독소패턴·연관위험을 부착합니다.

    절차(기획서 7장):
      1. 컬렉션별 배치 검색(search_many) — 조항 N개를 개별 검색하던 병목을 컬렉션당 1회로 축소
      2. 조항마다 reranker 재정렬 → sigmoid 정규화 → select_best_match → classify_clause_deviation
         (검색 후보가 아예 없으면 NO_MATCH, 후보는 있으나 임계 미달이면 EXTRA)
      3. use_toxic: toxic_patterns 역방향 검색 → detect_toxic_patterns 로 독소 패턴 부착
      4. CHANGED/MISSING 이탈에 grounder 로 법령 근거, graph 로 연관위험 조항 부착
      5. detect_missing_clauses 로 누락 표준조항 추가

    Args:
        retriever/reranker/grounder: 외부 I/O 포트(주입). graph 는 선택(없으면 연관위험 생략).
        match_threshold: 대응 표준조항으로 인정할 최소 정규화 점수(0~1).
        change_threshold: 매칭된 조항이 '충분히 같다'고 볼 본문 일치율.
        toxic_threshold: 독소 패턴으로 인정할 최소 정규화 점수(0~1).
        use_sub_chunk/use_toxic: 고도화 축 on/off (eval ablation 용).
    """
    results: List[DeviationResult] = []
    matched_ids: set[str] = set()
    standards_by_id = {std.clause_id: std for std in all_standard_clauses}
    type_filter = {"contract_type": contract_type.value}
    clause_texts = [clause.text for clause in clauses]

    # ── 1. 배치 검색: 조항별 개별 검색(N회)을 컬렉션당 1회로 축소 (임베딩 왕복 절감) ──
    empty_batch: List[List[Dict[str, Any]]] = [[] for _ in clauses]
    std_batch = (
        retriever.search_many(STANDARD_COLLECTION, clause_texts, "hybrid", type_filter, top_k)
        if clause_texts else []
    )
    sub_batch = (
        retriever.search_many(SUB_CHUNK_COLLECTION, clause_texts, "hybrid", type_filter, top_k)
        if (clause_texts and use_sub_chunk) else empty_batch
    )
    toxic_batch = (
        retriever.search_many(TOXIC_COLLECTION, clause_texts, "hybrid", None, top_k)
        if (clause_texts and use_toxic) else empty_batch
    )

    # ── 2. 조항별 재정렬·분류 (검색은 위에서 끝났고, 여기서는 조립·순수판정) ──
    for clause, std_raw, sub_raw, toxic_raw in zip(clauses, std_batch, sub_batch, toxic_batch):
        std_hits = reranker.rerank(clause.text, std_raw, text_key="text", top_k=top_k) if std_raw else []
        candidates = _clause_candidates(std_hits, standards_by_id, contract_type)

        sub_hits = reranker.rerank(clause.text, sub_raw, text_key="text", top_k=top_k) if sub_raw else []
        if sub_hits:
            sub_candidate = _sub_chunk_candidate(sub_hits, standards_by_id)
            if sub_candidate is not None:
                candidates.append(sub_candidate)

        # 독소 역방향 검색은 매칭 성패와 무관 (표준엔 없지만 사용자에게 해로운 EXTRA 조항 포착)
        toxic_hits = reranker.rerank(clause.text, toxic_raw, text_key="text", top_k=top_k) if toxic_raw else []
        toxic_patterns = _toxic_from_hits(toxic_hits, toxic_threshold) if toxic_hits else []

        # 매칭 판정: 후보가 아예 없으면 NO_MATCH, 있으면 EXTRA/CHANGED/NONE 분류
        if not std_hits and not sub_hits:
            deviation = Deviation.NO_MATCH
            matched_standard: Optional[StandardClause] = None
            score = 0.0
        else:
            matched_standard, score = select_best_match(candidates, match_threshold)
            deviation = classify_clause_deviation(
                user_text=clause.text,
                matched_standard=matched_standard,
                score=score,
                match_threshold=match_threshold,
                change_threshold=change_threshold,
            )

        grounding: List[GroundingLaw] = []
        related_risks: List[str] = []
        if matched_standard is not None:
            matched_ids.add(matched_standard.clause_id)
            if deviation == Deviation.CHANGED:
                grounding = _grounding_for(grounder, matched_standard.category)
                if graph is not None:
                    related_risks = graph.get_related_risks(matched_standard.clause_id)

        results.append(DeviationResult(
            user_clause=clause.text,
            matched_standard=matched_standard,
            deviation=deviation,
            confidence=score,
            grounding=grounding,
            toxic_patterns=toxic_patterns,
            related_risk_clauses=related_risks,
        ))

    # ── 3. 누락 탐지: 어떤 사용자 조항에도 매칭되지 않은 표준조항 → MISSING ──
    for missing_standard in detect_missing_clauses(all_standard_clauses, matched_ids):
        related = graph.get_related_risks(missing_standard.clause_id) if graph is not None else []
        results.append(DeviationResult(
            user_clause="",
            matched_standard=missing_standard,
            deviation=Deviation.MISSING,
            confidence=0.0,
            grounding=_grounding_for(grounder, missing_standard.category),
            related_risk_clauses=related,
        ))

    return results
