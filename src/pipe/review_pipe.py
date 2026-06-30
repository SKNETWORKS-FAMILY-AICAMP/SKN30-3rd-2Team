"""
[담당: 팀원 C + 리드] review_contract — 계약서 전체 검토 조립 (MCP 본체)

규격(통과해야 할 테스트): tests/pipe/test_review_pipe.py
참고 문서: src/pipe/README.md, src/core/README.md, 기획서 4·7장

core 의 순수 함수를 조립하고, 외부 작업(검색·법령)은 ports 로 주입받습니다.
⚠ 시그니처는 동결 MCP 계약(4장)에 가깝습니다 — 변경 시 PM/리드와 먼저 합의하세요.
"""
from typing import Any, Dict, List, Optional, Tuple
from contracts.enums import Category, ContractType, Deviation
from contracts.models import Clause, StandardClause, DeviationResult
from contracts.ports import Retriever, Grounder
from core import classify_clause_deviation, detect_missing_clauses, select_best_match


def _score_from_hit(hit: Dict[str, Any]) -> float:
    """검색 결과에서 가장 신뢰할 점수 필드를 골라 반환합니다."""
    for key in ("rerank_score", "fusion_score", "score"):
        value = hit.get(key)
        if value is not None:
            return float(value)
    return 0.0


def _standard_from_hit(
    hit: Dict[str, Any],
    standards_by_id: Dict[str, StandardClause],
    contract_type: ContractType,
) -> Optional[StandardClause]:
    """검색 결과 dict를 StandardClause로 변환합니다."""
    clause_id = hit.get("id") or hit.get("clause_id")
    if clause_id in standards_by_id:
        return standards_by_id[clause_id]

    if not clause_id:
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


def review_contract(
    clauses: List[Clause],
    contract_type: ContractType,
    *,
    retriever: Retriever,
    grounder: Grounder,
    all_standard_clauses: List[StandardClause],
    match_threshold: float = 0.5,
) -> List[DeviationResult]:
    """
    사용자 조항들을 표준조항과 비교해 이탈을 탐지하고 법령 근거를 부착합니다.

    절차(기획서 7장):
      1. 조항마다 retriever 로 표준조항 후보 검색 → select_best_match 로 최적 매칭
      2. classify_clause_deviation 로 MISSING/EXTRA/CHANGED/NONE 분류 (없으면 NO_MATCH)
      3. detect_missing_clauses 로 누락 표준조항 추가
      4. 매칭된 category 로 grounder 호출 → 법령 근거 부착
    """
    results: List[DeviationResult] = []
    matched_ids: set[str] = set()
    standards_by_id = {std.clause_id: std for std in all_standard_clauses}

    for clause in clauses:
        # 1. 검색: 사용자 조항 본문으로 표준조항 후보를 조회합니다.
        hits = retriever.search(
            "standard_clauses",
            clause.text,
            search_type="hybrid",
            metadata_filter={"contract_type": contract_type.value},
            top_k=5,
        )

        # 2. 검색 결과를 후보로 변환: dict 결과를 (StandardClause, score)로 바꿉니다.
        candidates: List[Tuple[StandardClause, float]] = []
        for hit in hits:
            standard = _standard_from_hit(hit, standards_by_id, contract_type)
            if standard is not None:
                candidates.append((standard, _score_from_hit(hit)))

        # 3. 최적 매칭 선택: core 함수로 최고 점수 후보와 임계치를 판정합니다.
        matched_standard, score = select_best_match(candidates, match_threshold)
        if matched_standard is None:
            # 4. 매칭 실패 처리: 빈 응답 대신 NO_MATCH 결과를 명시합니다.
            results.append(DeviationResult(
                user_clause=clause.text,
                matched_standard=None,
                deviation=Deviation.NO_MATCH,
                confidence=score,
            ))
            continue

        # 5. 이탈 분류: 사용자 조항과 매칭 표준조항의 본문 차이를 분류합니다.
        deviation = classify_clause_deviation(
            user_text=clause.text,
            matched_standard=matched_standard,
            score=score,
            match_threshold=match_threshold,
        )

        # 6. 법령 근거 부착: 매칭된 표준조항의 카테고리로 근거 조문을 조회합니다.
        grounding = grounder.get_grounding(matched_standard.category)

        # 7. 매칭 id 수집: 계약 전체 누락 탐지에 사용할 표준조항 id를 기록합니다.
        matched_ids.add(matched_standard.clause_id)

        # 8. 사용자 조항 결과 생성: 매칭/분류/근거를 DeviationResult로 묶습니다.
        results.append(DeviationResult(
            user_clause=clause.text,
            matched_standard=matched_standard,
            deviation=deviation,
            confidence=score,
            grounding=grounding,
        ))

    # 9. 누락 탐지: 어떤 사용자 조항에도 매칭되지 않은 표준조항을 찾습니다.
    for missing_standard in detect_missing_clauses(all_standard_clauses, matched_ids):
        # 10. MISSING 결과 추가: 누락 표준조항도 DeviationResult로 반환합니다.
        results.append(DeviationResult(
            user_clause="",
            matched_standard=missing_standard,
            deviation=Deviation.MISSING,
            confidence=0.0,
            grounding=grounder.get_grounding(missing_standard.category),
        ))

    return results
