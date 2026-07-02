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
import logging

logger = logging.getLogger(__name__)

from contracts.enums import Category, ContractType, Deviation, ToxicPattern
from contracts.models import Clause, StandardClause, StandardSubChunk, DeviationResult, GroundingLaw
from contracts.ports import Grounder, Graph
from adapter.port import Retriever, Reranker
from core import (
    check_coverage,
    classify_clause_deviation,
    detect_missing_clauses,
    detect_toxic_patterns,
    roll_up_sub_chunks,
    select_best_match,
    sigmoid,
    split_into_sub_chunks,
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
    toxic_threshold: float = 0.6,
    top_k: int = 5,
    toxic_top_k: int = 3,
    use_sub_chunk: bool = True,
    use_toxic: bool = True,
    all_standard_sub_chunks: Optional[Dict[str, List[StandardSubChunk]]] = None,
    coverage_threshold: float = 0.5,
    use_coverage: bool = True,
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
      6. use_coverage: 매칭 조항의 표준 서브청크가 사용자 조항에 모두 커버되는지 검사.
         미커버 항 존재 시 NONE → CHANGED 로 상향 (임베딩 희석으로 인한 오탐 방지, H 설계)

    Args:
        retriever: 벡터 DB·BM25 하이브리드 검색 포트. 배치 검색(search_many)으로 호출됩니다.
        reranker: 크로스 인코더 재정렬 포트. 후보 정렬뿐 아니라 커버리지 체크의 M×N
                  유사도 매트릭스 계산(compute_scores)에도 재사용됩니다.
        grounder: 이탈 조항(CHANGED/MISSING)에 관련 법령 근거를 부착하는 포트.
        all_standard_clauses: 계약 유형에 해당하는 표준조항 전체 목록.
                              MISSING 탐지 및 조항 코퍼스 조회에 사용합니다.
        graph: 연관위험 조항 탐색 포트. None 이면 연관위험 생략 (선택).
        match_threshold: 대응 표준조항으로 인정할 최소 정규화 점수(0~1, rerank_score→sigmoid).
        change_threshold: 매칭된 조항이 '충분히 같다'고 볼 본문 일치율
                          (항↔항 정렬 SequenceMatcher 기준 — core.calculate_text_similarity).
        toxic_threshold: 독소 패턴으로 인정할 최소 정규화 점수(0~1, rerank_score→sigmoid).
                         **0.5 는 sigmoid 바닥값과 겹쳐 무신호 후보까지 전부 통과하므로 금지.**
                         v1 골든 점수 분포상 0.6 이 특이도 0→0.86 로 축퇴를 해소하는 시작값이며,
                         리랭커가 다수 독소에 바닥 점수만 주는 한계가 있어 recall·특이도 동시 확보는
                         어렵다(임계 상향 시 recall 하락). 확대 골든셋으로 재보정 대상.
        top_k: 표준/서브청크 컬렉션 검색·재정렬 시 가져올 상위 후보 수.
        toxic_top_k: 독소 컬렉션 전용 후보 수. 독소는 상위 소수만 유의미하고 나머지는 바닥 점수
                     노이즈라 별도로 작게 둔다(무의미 후보가 top_k 를 채우는 것을 방지).
        use_sub_chunk: True 이면 standard_sub_chunks 컬렉션 검색 + Max Roll-up 수행.
                       False 이면 조 단위 임베딩만 사용 (ablation 비교군 A).
        use_toxic: True 이면 toxic_patterns 역방향 검색·독소 패턴 부착 수행.
        all_standard_sub_chunks: {parent_clause_id → [StandardSubChunk, ...]} 맵.
                                 커버리지 체크에 필요하며, None 이면 use_coverage 가 True 여도
                                 커버리지 체크를 건너뜁니다. 호출부에서 SQLite 로 미리 로드 후
                                 주입합니다(all_standard_clauses 패턴과 동일).
        coverage_threshold: 표준 서브chunk가 '커버됨'으로 인정할 최소 유사도(0~1, sigmoid 스케일).
                            match_threshold·change_threshold 와 독립 파라미터이므로
                            eval 캘리브레이션으로 별도 조정합니다.
        use_coverage: True 이면 서브청크 커버리지 체크 수행, NONE → CHANGED 상향 활성화.
                      False 이면 체크 전체 스킵 (ablation 비교군 A 재현 및 단위 테스트용).
    """
    logger.info(
        f"[review_contract] 검토 프로세스 시작: contract_type={contract_type.value}, "
        f"입력 조항 수={len(clauses)}개, 표준 코퍼스 크기={len(all_standard_clauses)}개"
    )

    results: List[DeviationResult] = []
    matched_ids: set[str] = set()
    standards_by_id = {std.clause_id: std for std in all_standard_clauses}
    type_filter = {"contract_type": contract_type.value}
    clause_texts = [clause.text for clause in clauses]

    # ── 1. 배치 검색: 조항별 개별 검색(N회)을 컬렉션당 1회로 축소 (임베딩 왕복 절감) ──
    logger.info("[review_contract] 1단계: 벡터 DB 배치 검색을 수행합니다 (표준/서브청크/독소).")
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
        retriever.search_many(TOXIC_COLLECTION, clause_texts, "hybrid", None, toxic_top_k)
        if (clause_texts and use_toxic) else empty_batch
    )
    logger.info(
        f"[review_contract] 배치 검색 완료: std_batch={len(std_batch)}건, "
        f"sub_batch={len(sub_batch)}건, toxic_batch={len(toxic_batch)}건"
    )

    # ── 2. 배치 재정렬: 조항별 rerank(N회)를 컬렉션당 1회로 축소 (cross-encoder 배치 채움) ──
    logger.info("[review_contract] 2단계: 조항별 재정렬(Rerank) 및 이탈(Deviation) 분류를 수행합니다.")
    std_hits_batch = reranker.rerank_many(clause_texts, std_batch, text_key="text", top_k=top_k)
    sub_hits_batch = reranker.rerank_many(clause_texts, sub_batch, text_key="text", top_k=top_k)
    toxic_hits_batch = reranker.rerank_many(clause_texts, toxic_batch, text_key="text", top_k=toxic_top_k)

    # ── 조항별 분류 (검색·재정렬은 위에서 끝났고, 여기서는 조립·순수판정) ──
    # 1차 패스: 기본 분류 후, 커버리지 대상 조항의 (표준 항, 사용자 항) 쌍을 수집만 한다.
    # M×N 유사도 계산을 조항마다 개별 호출하지 않고, 전 조항의 쌍을 모아 compute_scores_many 로
    # 단 1회 배치 계산한다(std/sub/toxic rerank 배치화와 동일 취지).
    pending: List[Dict[str, Any]] = []
    cov_queries: List[str] = []               # 커버리지 대상 표준 항 텍스트(전 조항 flatten)
    cov_docs_per_query: List[List[str]] = []   # 각 표준 항에 대응하는 사용자 항 텍스트 목록

    for i, (clause, std_hits, sub_hits, toxic_hits) in enumerate(
        zip(clauses, std_hits_batch, sub_hits_batch, toxic_hits_batch), 1
    ):
        candidates = _clause_candidates(std_hits, standards_by_id, contract_type)

        if sub_hits:
            sub_candidate = _sub_chunk_candidate(sub_hits, standards_by_id)
            if sub_candidate is not None:
                candidates.append(sub_candidate)

        # 독소 역방향 검색은 매칭 성패와 무관 (표준엔 없지만 사용자에게 해로운 EXTRA 조항 포착)
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

        # 매칭된 표준조항은 커버리지 결과와 무관하게 '커버됨'으로 기록 (MISSING 탐지용)
        if matched_standard is not None:
            matched_ids.add(matched_standard.clause_id)

        entry: Dict[str, Any] = {
            "idx": i,
            "clause": clause,
            "deviation": deviation,
            "matched_standard": matched_standard,
            "score": score,
            "toxic_patterns": toxic_patterns,
            "std_ids": None,     # 커버리지 대상일 때만 채워짐
            "cov_start": 0,      # cov_queries 내 이 조항의 행 시작 인덱스
            "cov_count": 0,      # 이 조항이 기여한 표준 항(행) 수
        }

        # ── 커버리지 대상 판별: NONE 판정된 거대 조항 → 실제 M×N 계산은 뒤에서 배치로 ──
        # 조건: use_coverage ON, 매칭 성공, 현재 NONE(이미 CHANGED면 중복 불필요),
        #       all_standard_sub_chunks 주입됨, 해당 부모의 서브청크가 2개 이상(거대 조항)
        if (
            use_coverage
            and matched_standard is not None
            and deviation == Deviation.NONE
            and all_standard_sub_chunks is not None
        ):
            std_subs = all_standard_sub_chunks.get(matched_standard.clause_id, [])
            if len(std_subs) >= 2:
                user_sub_texts = split_into_sub_chunks(clause.text)
                entry["std_ids"] = [s.sub_chunk_id for s in std_subs]
                entry["cov_start"] = len(cov_queries)
                entry["cov_count"] = len(std_subs)
                # 각 표준 항을 쿼리로, 사용자 항 전체를 문서로 flatten (행 = 표준 항)
                for s in std_subs:
                    cov_queries.append(s.text)
                    cov_docs_per_query.append(user_sub_texts)

        pending.append(entry)

    # ── 커버리지 배치 계산: 전 조항의 (표준 항, 사용자 항) 쌍을 단일 호출로 채점 ──
    cov_scores = (
        reranker.compute_scores_many(cov_queries, cov_docs_per_query)
        if cov_queries else []
    )

    # 2차 패스: 커버리지 결과 반영(NONE→CHANGED) 후 근거·연관위험 부착해 결과 조립
    for entry in pending:
        clause = entry["clause"]
        deviation = entry["deviation"]
        matched_standard = entry["matched_standard"]
        uncovered_ids: List[str] = []

        if entry["cov_count"]:
            start = entry["cov_start"]
            # 각 행 j = 표준 항 j 와 사용자 항 N개 간 sigmoid 점수 (배치 결과 슬라이스)
            matrix = [
                [sigmoid(raw) for raw in cov_scores[start + j]]
                for j in range(entry["cov_count"])
            ]
            covered, uncovered_ids = check_coverage(entry["std_ids"], matrix, coverage_threshold)
            if not covered:
                deviation = Deviation.CHANGED
                logger.info(
                    f"[review_contract] 조항 #{entry['idx']} ({matched_standard.clause_id}) 표준 항 미커버 감지 -> "
                    f"NONE에서 CHANGED로 상향 조정 (미커버 항 ID: {uncovered_ids})"
                )

        grounding: List[GroundingLaw] = []
        related_risks: List[str] = []
        if matched_standard is not None and deviation == Deviation.CHANGED:
            grounding = _grounding_for(grounder, matched_standard.category)
            if graph is not None:
                related_risks = graph.get_related_risks(matched_standard.clause_id)

        results.append(DeviationResult(
            user_clause=clause.text,
            matched_standard=matched_standard,
            deviation=deviation,
            confidence=entry["score"],
            grounding=grounding,
            toxic_patterns=entry["toxic_patterns"],
            related_risk_clauses=related_risks,
            uncovered_sub_chunk_ids=uncovered_ids,
        ))

    logger.info(f"[review_contract] 조항별 재정렬/분류 완료. 매칭된 유니크 표준조항 수: {len(matched_ids)}개")

    # ── 3. 누락 탐지: 어떤 사용자 조항에도 매칭되지 않은 표준조항 → MISSING ──
    logger.info("[review_contract] 3단계: 누락된 표준조항(MISSING) 탐지를 수행합니다.")
    missing_clauses = detect_missing_clauses(all_standard_clauses, matched_ids)
    logger.info(f"[review_contract] 누락 표준조항 탐지 결과: {len(missing_clauses)}건 누락 확인")

    for missing_standard in missing_clauses:
        related = graph.get_related_risks(missing_standard.clause_id) if graph is not None else []
        results.append(DeviationResult(
            user_clause="",
            matched_standard=missing_standard,
            deviation=Deviation.MISSING,
            confidence=0.0,
            grounding=_grounding_for(grounder, missing_standard.category),
            related_risk_clauses=related,
        ))

    logger.info(
        f"[review_contract] 검토 프로세스 완료: 최종 반환 결과 수={len(results)}건 "
        f"(사용자조항 판정={len(clauses)}건, 누락추가={len(missing_clauses)}건)"
    )
    return results
