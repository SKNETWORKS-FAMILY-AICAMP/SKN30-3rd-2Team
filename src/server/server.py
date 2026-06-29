import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from contracts.enums import ContractType, Category
from contracts.models import StandardClause
from contracts.implement import KordocParser, KoreanLawGrounder
from adapter import vector, db
from pipe.review_pipe import review_contract as review_contract_pipe
from pipe.exceptions import EmptyDocumentError, CorpusUnavailableError, InvalidConfigError, PipelineIntegrityError
from server.dto import (
    ParseContractResponse,
    GetGroundingResponse,
    MatchClauseResponse,
    MatchCandidate,
    ReviewContractResponse,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("WorkShield")

# 싱글턴 어댑터
_parser = KordocParser()
_grounder = KoreanLawGrounder()


@mcp.tool()
def parse_contract(file_path: str, contract_type: Optional[str] = None) -> ParseContractResponse:
    """
    계약서 파일(HWP/PDF)을 조항 단위로 분해하여 반환합니다.

    Args:
        file_path: 분석할 계약서 파일의 절대 경로
        contract_type: 계약 종류 컨텍스트 (SW_FREELANCE / SW_EMPLOYMENT / ARTS_SERVICE). 생략 가능.
    """
    ct: Optional[ContractType] = None
    if contract_type is not None:
        try:
            ct = ContractType(contract_type)
        except ValueError:
            raise ValueError(
                f"지원하지 않는 계약 종류: '{contract_type}'. "
                f"가능한 값: {[e.value for e in ContractType]}"
            )

    # FileNotFoundError · RuntimeError(kordoc 변환 실패) → 그대로 raise → FastMCP error 응답
    clauses = _parser.parse(file_path)

    if not clauses:
        return ParseContractResponse(
            status="EMPTY_DOCUMENT",
            contract_type=ct.value if ct else None,
            clauses=[],
            message="조항을 찾을 수 없습니다. 스캔 PDF이거나 '제N조' 형식이 없는 문서일 가능성이 있습니다.",
        )

    return ParseContractResponse(
        status="OK",
        contract_type=ct.value if ct else None,
        clauses=clauses,
    )


_MATCH_TOP_K_MAX = 10
_STANDARD_CLAUSES_TABLE = "standard_clauses"


def _load_standards(ct: ContractType) -> list[StandardClause]:
    rows = db.fetch_all(
        "SELECT * FROM standard_clauses WHERE contract_type = ?",
        ct.value,
    )
    return [StandardClause(**row) for row in rows]
_STANDARD_CLAUSES_COLLECTION = "standard_clauses"


@mcp.tool()
def match_clause(
    clause_text: str,
    contract_type: str,
    top_k: int = 5,
) -> MatchClauseResponse:
    """
    단일 조항 텍스트와 가장 유사한 표준조항 후보를 검색합니다.

    Args:
        clause_text: 검색할 사용자 조항 본문 텍스트
        contract_type: 계약 종류 (SW_FREELANCE / SW_EMPLOYMENT / ARTS_SERVICE)
        top_k: 반환할 후보 수. 최대 10. 기본값 5.
    """
    try:
        ct = ContractType(contract_type)
    except ValueError:
        raise ValueError(
            f"지원하지 않는 계약 종류: '{contract_type}'. "
            f"가능한 값: {[e.value for e in ContractType]}"
        )

    top_k = min(top_k, _MATCH_TOP_K_MAX)

    results = vector.search(
        collection_name=_STANDARD_CLAUSES_COLLECTION,
        query=clause_text,
        search_type="hybrid",
        metadata_filter={"contract_type": ct.value},
        top_k=top_k,
    )

    if not results:
        return MatchClauseResponse(
            status="NO_RESULT",
            contract_type=ct.value,
            candidates=[],
            message="일치하는 표준조항을 찾지 못했습니다.",
        )

    candidates = [
        MatchCandidate(
            clause_id=r["id"],
            score=r.get("fusion_score") or r.get("bm25_score") or r.get("dense_distance") or 0.0,
            standard_text=r["text"],
            title=r.get("title", ""),
            category=r.get("category", ""),
            source=r.get("source", ""),
        )
        for r in results
    ]

    return MatchClauseResponse(
        status="OK",
        contract_type=ct.value,
        candidates=candidates,
    )


@mcp.tool()
def get_grounding(
    category: Optional[str] = None,
    clause_text: Optional[str] = None,
) -> GetGroundingResponse:
    """
    카테고리 또는 조항 본문에 해당하는 관련 법령 조문을 조회합니다.
    둘 다 제공되면 clause_text를 우선합니다 (korean-law-mcp는 단일 쿼리만 지원).

    Args:
        category: 조항 분류 카테고리 (PAYMENT / IP_OWNERSHIP / DERIVATIVE_WORK 등). 생략 가능.
        clause_text: 법령 조문을 조회할 조항 본문 텍스트. 생략 가능.
    """
    if category is None and clause_text is None:
        return GetGroundingResponse(
            status="INVALID_INPUT",
            grounding=[],
            message="category 또는 clause_text 중 하나 이상을 입력해야 합니다.",
        )

    if clause_text is not None:
        grounding = _grounder.query_law(clause_text)
    else:
        try:
            ct = Category(category)
        except ValueError:
            raise ValueError(
                f"지원하지 않는 카테고리: '{category}'. "
                f"가능한 값: {[e.value for e in Category]}"
            )
        grounding = _grounder.get_grounding(ct)

    if not grounding:
        return GetGroundingResponse(
            status="NO_RESULT",
            grounding=[],
            message="관련 법령 조문을 찾지 못했습니다.",
        )

    return GetGroundingResponse(status="OK", grounding=grounding)


@mcp.tool()
def review_contract(file_path: str, contract_type: str) -> ReviewContractResponse:
    """
    계약서 파일 전체를 검토합니다. 파싱 → 표준조항 매칭 → 이탈 분류 → 법령 근거 부착 순으로 실행합니다.

    Args:
        file_path: 검토할 계약서 파일의 절대 경로 (HWP / PDF)
        contract_type: 계약 종류 (SW_FREELANCE / SW_EMPLOYMENT / ARTS_SERVICE)
    """
    try:
        ct = ContractType(contract_type)
    except ValueError:
        raise ValueError(
            f"지원하지 않는 계약 종류: '{contract_type}'. "
            f"가능한 값: {[e.value for e in ContractType]}"
        )

    # FileNotFoundError · RuntimeError(kordoc 실패) → 그대로 raise → FastMCP error 응답
    clauses = _parser.parse(file_path)
    if not clauses:
        return ReviewContractResponse(
            status="EMPTY_DOCUMENT",
            contract_type=ct.value,
            results=[],
            message="조항을 찾을 수 없습니다. 스캔 PDF이거나 '제N조' 형식이 없는 문서일 가능성이 있습니다.",
        )

    standards = _load_standards(ct)
    if not standards:
        return ReviewContractResponse(
            status="CORPUS_UNAVAILABLE",
            contract_type=ct.value,
            results=[],
            message=f"{ct.value} 표준 코퍼스가 DB에 없습니다. `just build-db`를 먼저 실행하세요.",
        )

    try:
        results = review_contract_pipe(
            clauses=clauses,
            contract_type=ct,
            retriever=vector,
            grounder=_grounder,
            all_standard_clauses=standards,
        )
    except InvalidConfigError as e:
        return ReviewContractResponse(
            status="INVALID_CONFIG",
            contract_type=ct.value,
            results=[],
            message=str(e),
        )
    except PipelineIntegrityError as e:
        logger.error(f"[CRITICAL] 파이프라인 무결성 오류: {e}")
        return ReviewContractResponse(
            status="PIPELINE_ERROR",
            contract_type=ct.value,
            results=[],
            message="내부 오류가 발생했습니다. 관리자에게 문의하세요.",
        )
    except (CorpusUnavailableError, EmptyDocumentError) as e:
        # review_pipe 내부에서 raise된 경우 (이중 방어)
        logger.warning(f"review_pipe 내부 도메인 예외: {e}")
        return ReviewContractResponse(
            status="PIPELINE_ERROR",
            contract_type=ct.value,
            results=[],
            message=str(e),
        )
    except NotImplementedError:
        return ReviewContractResponse(
            status="PIPELINE_ERROR",
            contract_type=ct.value,
            results=[],
            message="review_contract 미구현 상태입니다. 담당자(팀원 C)에게 문의하세요.",
        )

    return ReviewContractResponse(
        status="OK",
        contract_type=ct.value,
        results=results,
    )


if __name__ == "__main__":
    mcp.run()
