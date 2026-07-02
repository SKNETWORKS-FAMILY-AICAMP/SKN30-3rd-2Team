import base64
import binascii
import logging
import uuid
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from config import BASE_DIR
from contracts.enums import ContractType, Category, Deviation, ToxicPattern
from contracts.models import StandardClause, StandardSubChunk
from adapter import vector, db, reranker
from server.deps import get_parser, get_grounder
from core import classify_clause_deviation, select_best_match, sigmoid
from pipe.review_pipe import review_contract as review_contract_pipe
from pipe.exceptions import EmptyDocumentError, CorpusUnavailableError, InvalidConfigError, PipelineIntegrityError
from server.dto import (
    ParseContractResponse,
    GetGroundingResponse,
    MatchClauseResponse,
    MatchCandidate,
    ReviewContractResponse,
    ClassifyClauseResponse,
    ListContractTypesResponse,
    CategoryInfo,
    ListCategoriesResponse,
    ListToxicPatternsResponse,
)

logger = logging.getLogger(__name__)

# 네트워크(streamable-http) 배포에서는 클라이언트와 서버가 파일시스템을 공유하지 않으므로,
# file_content(base64)로 받은 계약서를 이 디렉터리에 임시로 내려쓴 뒤 기존 file_path 경로로 처리한다.
# (data/README.md, .gitignore: 사용자 업로드 임시 파일 전용 디렉터리)
_UPLOAD_DIR = BASE_DIR / "data" / "99_uploads"


def _resolve_contract_file(
    file_path: Optional[str], file_content: Optional[str], file_name: Optional[str]
) -> tuple[str, Optional[Path]]:
    """file_path(로컬 경로) 또는 file_content(base64)+file_name 중 하나를 받아 실제 파일 경로를 반환한다.

    base64 입력인 경우 디코딩한 내용을 _UPLOAD_DIR에 임시 파일로 저장하고, 그 Path를 함께 반환하여
    호출부(도구 함수)가 사용 후 삭제하도록 한다. file_path 입력인 경우 두 번째 값은 None(정리 불필요).
    """
    if file_path and (file_content or file_name):
        raise ValueError("file_path와 file_content/file_name은 동시에 지정할 수 없습니다.")
    if file_path:
        return file_path, None
    if not file_content or not file_name:
        raise ValueError(
            "file_path 또는 (file_content, file_name) 조합 중 하나를 입력해야 합니다. "
            "file_content는 base64 인코딩된 파일 바이트, file_name은 확장자 판별용 원본 파일명입니다."
        )

    try:
        raw = base64.b64decode(file_content, validate=True)
    except binascii.Error as e:
        raise ValueError(f"file_content가 올바른 base64 형식이 아닙니다: {e}") from e

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = _UPLOAD_DIR / f"{uuid.uuid4().hex}{Path(file_name).suffix}"
    temp_path.write_bytes(raw)
    return str(temp_path), temp_path

mcp = FastMCP("WorkShield")


@mcp.tool()
def parse_contract(
    file_path: Optional[str] = None,
    file_content: Optional[str] = None,
    file_name: Optional[str] = None,
    contract_type: Optional[str] = None,
) -> ParseContractResponse:
    """
    계약서 파일(HWP/PDF)을 조항 단위로 분해하여 반환합니다. 검토 파이프라인의 1단계이며,
    이 결과를 사람이 조항을 골라 match_clause/classify_clause 로 부분 검토하는 데도 쓸 수 있습니다.

    이탈 판정은 하지 않습니다 — 조항 분해만 수행합니다. 판정이 필요하면 review_contract 또는
    classify_clause 를 이어서 호출하세요.

    Args:
        file_path: 분석할 계약서 파일의 절대 경로 (서버와 파일시스템을 공유할 때만 사용 가능. 로컬 stdio 배포용)
        file_content: base64 인코딩된 계약서 파일 바이트 (네트워크 배포용). file_name과 함께 지정해야 함.
        file_name: 원본 파일명 (확장자 판별용). file_content와 함께 지정해야 함.
        contract_type: 계약 종류 컨텍스트. 생략 가능. 가능한 값은 list_contract_types 로 조회하세요
            (하드코딩 금지 — 값 집합이 바뀔 수 있음).
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

    resolved_path, temp_path = _resolve_contract_file(file_path, file_content, file_name)
    try:
        # FileNotFoundError · RuntimeError(kordoc 변환 실패) → 그대로 raise → FastMCP error 응답
        clauses = get_parser().parse(resolved_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

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


def _load_sub_chunks(ct: ContractType) -> dict[str, list[StandardSubChunk]]:
    """계약 유형별 표준 서브청크를 {parent_clause_id → [StandardSubChunk, ...]} 로 로드합니다.

    review_contract 의 의미 커버리지 게이트 입력. 미주입 시 커버리지 체크가 스킵되고 difflib
    폴백으로 내려가 실계약에서 NONE 도달이 불가해집니다(v1_review Track B §3). 오프라인
    서브청크 인덱스(`just build-db`)가 준비돼 있어야 합니다.
    """
    rows = db.fetch_all(
        "SELECT * FROM standard_sub_chunks WHERE contract_type = ? "
        "ORDER BY parent_clause_id, sub_chunk_index",
        ct.value,
    )
    by_parent: dict[str, list[StandardSubChunk]] = {}
    for row in rows:
        sub = StandardSubChunk(**row)
        by_parent.setdefault(sub.parent_clause_id, []).append(sub)
    return by_parent
_STANDARD_CLAUSES_COLLECTION = "standard_clauses"


@mcp.tool()
def match_clause(
    clause_text: str,
    contract_type: str,
    top_k: int = 5,
) -> MatchClauseResponse:
    """
    단일 조항 텍스트와 가장 유사한 표준조항 후보를 유사도 순으로 검색합니다 (검색 전용, 이탈 판정 없음).

    이 도구는 "비슷한 표준조항이 뭐가 있나"만 답합니다. score는 검색 융합 점수(RRF/BM25 등)이며
    match_threshold 같은 판정 임계치와 스케일이 다르므로 "매칭 성공/실패"를 이 점수로 판단하지 마세요.
    "이 조항이 표준 대비 이탈(MISSING/EXTRA/CHANGED/NONE)인가?"가 필요하면 classify_clause 를 쓰세요.
    이 도구가 반환하는 것은 "검토 후보" 목록일 뿐 최종 판정이 아닙니다.

    사용 예: 계약서 전체가 아니라 특정 조항 하나에 대해 어떤 표준조항이 대응되는지만 빠르게 훑어볼 때.

    Args:
        clause_text: 검색할 사용자 조항 본문 텍스트
        contract_type: 계약 종류. 가능한 값은 list_contract_types 로 조회하세요.
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

    반환되는 법령 조문은 참고용 근거 자료이며, "이 조항은 위법이다/유리하다" 같은 결론은
    포함하지 않습니다. 그런 해석이 필요한 문장은 이 도구의 출력을 그대로 사용자에게
    전달하지 말고, 반드시 "검토 후보/참고 자료"로 프레이밍하세요.

    Args:
        category: 조항 분류 카테고리. 가능한 값은 list_categories 로 조회하세요. 생략 가능.
        clause_text: 법령 조문을 조회할 조항 본문 텍스트. 생략 가능.
    """
    if category is None and clause_text is None:
        return GetGroundingResponse(
            status="INVALID_INPUT",
            grounding=[],
            message="category 또는 clause_text 중 하나 이상을 입력해야 합니다.",
        )

    if clause_text is not None:
        grounding = get_grounder().query_law(clause_text)
    else:
        try:
            ct = Category(category)
        except ValueError:
            raise ValueError(
                f"지원하지 않는 카테고리: '{category}'. "
                f"가능한 값: {[e.value for e in Category]}"
            )
        grounding = get_grounder().get_grounding(ct)

    if not grounding:
        return GetGroundingResponse(
            status="NO_RESULT",
            grounding=[],
            message="관련 법령 조문을 찾지 못했습니다.",
        )

    return GetGroundingResponse(status="OK", grounding=grounding)


@mcp.tool()
def review_contract(
    contract_type: str,
    file_path: Optional[str] = None,
    file_content: Optional[str] = None,
    file_name: Optional[str] = None,
) -> ReviewContractResponse:
    """
    계약서 파일 전체를 검토합니다. 파싱 → 표준조항 매칭 → 이탈 분류 → 법령 근거 부착 순으로 실행합니다.
    조항이 많은 계약서는 처리에 시간이 걸릴 수 있습니다(전체 조항을 배치로 검색·재정렬).

    결과의 각 항목은 "이탈 검토 후보"입니다 — MISSING/EXTRA/CHANGED 판정 자체가 "위법/불리함"을
    단정하는 것은 아니며, 표준조항과의 기계적 차이를 표시할 뿐입니다. 사용자에게 전달할 때도
    이 프레이밍(검토 후보)을 유지하세요.

    특정 조항 한두 개만 빠르게 보고 싶다면 이 도구 대신 parse_contract 로 조항을 나눈 뒤
    classify_clause 를 개별 호출하는 편이 더 빠릅니다.

    Args:
        contract_type: 계약 종류. 가능한 값은 list_contract_types 로 조회하세요.
        file_path: 검토할 계약서 파일의 절대 경로 (서버와 파일시스템을 공유할 때만 사용 가능. 로컬 stdio 배포용)
        file_content: base64 인코딩된 계약서 파일 바이트 (네트워크 배포용). file_name과 함께 지정해야 함.
        file_name: 원본 파일명 (확장자 판별용). file_content와 함께 지정해야 함.
    """
    try:
        ct = ContractType(contract_type)
    except ValueError:
        raise ValueError(
            f"지원하지 않는 계약 종류: '{contract_type}'. "
            f"가능한 값: {[e.value for e in ContractType]}"
        )

    resolved_path, temp_path = _resolve_contract_file(file_path, file_content, file_name)
    try:
        # FileNotFoundError · RuntimeError(kordoc 실패) → 그대로 raise → FastMCP error 응답
        clauses = get_parser().parse(resolved_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
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
            reranker=reranker,
            grounder=get_grounder(),
            all_standard_clauses=standards,
            all_standard_sub_chunks=_load_sub_chunks(ct),
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


_CLASSIFY_TOP_K = 5


@mcp.tool()
def classify_clause(
    clause_text: str,
    contract_type: str,
    match_threshold: float = 0.5,
    change_threshold: float = 0.85,
) -> ClassifyClauseResponse:
    """
    단일 조항 텍스트 하나를 표준조항과 비교해 이탈 여부를 판정합니다 (부분 검토 워크플로우용).

    review_contract 전체를 돌리지 않고 "이 조항 하나만" 표준 대비 어떤지 알고 싶을 때 씁니다.
    match_clause 가 후보 나열까지만 하는 것과 달리, 이 도구는 재정렬(reranker) → 최적 매칭 선택
    → 이탈 분류까지 끝내 deviation(NO_MATCH/EXTRA/CHANGED/NONE) 하나를 확정해 반환합니다.

    MISSING은 이 도구로 나오지 않습니다. MISSING은 "표준조항이 계약서 전체에 없다"는 뜻이라
    조항 하나만으로는 판정할 수 없고, review_contract 로 전체를 봐야 발견됩니다.
    반환되는 deviation은 표준 대비 기계적 차이를 나타내는 "검토 후보" 표식이며, 위법 여부나
    유불리를 단정하지 않습니다.

    Args:
        clause_text: 판정할 사용자 조항 본문 텍스트
        contract_type: 계약 종류. 가능한 값은 list_contract_types 로 조회하세요.
        match_threshold: 대응 표준조항으로 인정할 최소 정규화 점수(0~1). 기본값 0.5.
        change_threshold: 매칭된 조항이 '충분히 같다'고 볼 본문 일치율. 기본값 0.85.
    """
    try:
        ct = ContractType(contract_type)
    except ValueError:
        raise ValueError(
            f"지원하지 않는 계약 종류: '{contract_type}'. "
            f"가능한 값: {[e.value for e in ContractType]}"
        )

    standards = _load_standards(ct)
    if not standards:
        return ClassifyClauseResponse(
            status="CORPUS_UNAVAILABLE",
            contract_type=ct.value,
            message=f"{ct.value} 표준 코퍼스가 DB에 없습니다. `just build-db`를 먼저 실행하세요.",
        )
    standards_by_id = {std.clause_id: std for std in standards}

    raw_hits = vector.search(
        collection_name=_STANDARD_CLAUSES_COLLECTION,
        query=clause_text,
        search_type="hybrid",
        metadata_filter={"contract_type": ct.value},
        top_k=_CLASSIFY_TOP_K,
    )
    if not raw_hits:
        return ClassifyClauseResponse(
            status="OK",
            contract_type=ct.value,
            deviation=Deviation.NO_MATCH.value,
            confidence=0.0,
        )

    reranked = reranker.rerank(clause_text, raw_hits, text_key="text", top_k=_CLASSIFY_TOP_K)
    candidates = []
    for hit in reranked:
        clause_id = hit.get("id") or hit.get("clause_id")
        standard = standards_by_id.get(clause_id) if clause_id else None
        if standard is not None:
            score = sigmoid(float(hit["rerank_score"])) if "rerank_score" in hit else 0.0
            candidates.append((standard, score))

    matched, score = select_best_match(candidates, match_threshold)
    deviation = classify_clause_deviation(
        user_text=clause_text,
        matched_standard=matched,
        score=score,
        match_threshold=match_threshold,
        change_threshold=change_threshold,
    )

    grounding = []
    if matched is not None and deviation == Deviation.CHANGED and matched.category != Category.GENERAL:
        grounding = get_grounder().get_grounding(matched.category)

    return ClassifyClauseResponse(
        status="OK",
        contract_type=ct.value,
        deviation=deviation.value,
        confidence=score,
        matched_standard=matched,
        grounding=grounding,
    )


@mcp.tool()
def list_contract_types() -> ListContractTypesResponse:
    """
    지원하는 계약 종류(contract_type) 전체 목록을 조회합니다.

    parse_contract / match_clause / review_contract / classify_clause 의 contract_type
    인자에 어떤 값을 넣을 수 있는지 하드코딩하지 말고 이 도구로 런타임에 확인하세요
    (지원 목록은 버전에 따라 추가/제거될 수 있습니다).
    """
    return ListContractTypesResponse(contract_types=[e.value for e in ContractType])


@mcp.tool()
def list_categories() -> ListCategoriesResponse:
    """
    조항 분류 카테고리(category) 전체 목록을 설명·앵커 키워드와 함께 조회합니다.

    get_grounding 의 category 인자 값을 확인하거나, 계약서의 어떤 카테고리들이
    검토 대상인지 사람에게 설명할 때 사용하세요.
    """
    return ListCategoriesResponse(
        categories=[
            CategoryInfo(value=c.value, description=c.description, anchors=list(c.anchors))
            for c in Category
        ]
    )


@mcp.tool()
def list_toxic_patterns() -> ListToxicPatternsResponse:
    """
    탐지 대상 독소조항 패턴(toxic_pattern) 전체 목록을 조회합니다.

    review_contract 결과의 toxic_patterns 필드에 어떤 값이 나올 수 있는지 확인할 때 사용하세요.
    """
    return ListToxicPatternsResponse(patterns=[p.value for p in ToxicPattern])


@mcp.resource("standard://{contract_type}")
def list_standard_clauses(contract_type: str) -> list[dict]:
    """계약 유형별 표준조항 목록을 (clause_id, title, category) 요약으로 읽기 전용 브라우징합니다.

    본문 전체가 필요하면 standard://{contract_type}/{clause_id} 를 읽으세요.
    """
    try:
        ct = ContractType(contract_type)
    except ValueError:
        raise ValueError(
            f"지원하지 않는 계약 종류: '{contract_type}'. "
            f"가능한 값: {[e.value for e in ContractType]}"
        )
    rows = db.fetch_all(
        "SELECT clause_id, title, category FROM standard_clauses WHERE contract_type = ?",
        ct.value,
    )
    return rows


@mcp.resource("standard://{contract_type}/{clause_id}")
def get_standard_clause(contract_type: str, clause_id: str) -> dict:
    """표준조항 원문 전체(제목·본문·출처·버전)를 clause_id로 조회합니다."""
    try:
        ContractType(contract_type)
    except ValueError:
        raise ValueError(
            f"지원하지 않는 계약 종류: '{contract_type}'. "
            f"가능한 값: {[e.value for e in ContractType]}"
        )
    row = db.fetch_one(
        "SELECT * FROM standard_clauses WHERE contract_type = ? AND clause_id = ?",
        (contract_type, clause_id),
    )
    if row is None:
        raise ValueError(f"표준조항을 찾을 수 없습니다: contract_type={contract_type}, clause_id={clause_id}")
    return row