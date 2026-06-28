"""
[담당: 팀원 C + 리드] review_contract — 계약서 전체 검토 조립 (MCP 본체)

규격(통과해야 할 테스트): tests/pipe/test_review_pipe.py
참고 문서: src/pipe/README.md, src/core/README.md, 기획서 4·7장

core 의 순수 함수를 조립하고, 외부 작업(검색·법령)은 ports 로 주입받습니다.
⚠ 시그니처는 동결 MCP 계약(4장)에 가깝습니다 — 변경 시 PM/리드와 먼저 합의하세요.
"""
from typing import List
from contracts.enums import ContractType
from contracts.models import Clause, StandardClause, DeviationResult
from contracts.ports import Retriever, Grounder


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
    # TODO(팀원 C/리드): core 함수 조립으로 구현.
    #   from core import select_best_match, classify_clause_deviation, detect_missing_clauses
    #   - 빈 검색 결과는 DeviationResult(deviation=NO_MATCH) 로 (빈 응답 금지, 4.2)
    raise NotImplementedError("담당: 팀원 C/리드 — tests/pipe/test_review_pipe.py 를 통과시키세요.")
