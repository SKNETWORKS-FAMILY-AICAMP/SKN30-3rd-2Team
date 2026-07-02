from typing import Literal, Optional
from pydantic import BaseModel, Field
from contracts.models import Clause, GroundingLaw, DeviationResult, StandardClause


class ParseContractResponse(BaseModel):
    status: Literal["OK", "EMPTY_DOCUMENT"]
    contract_type: Optional[str] = None
    clauses: list[Clause]
    message: Optional[str] = None


class GetGroundingResponse(BaseModel):
    status: Literal["OK", "NO_RESULT", "INVALID_INPUT"]
    grounding: list[GroundingLaw]
    message: Optional[str] = None


class MatchCandidate(BaseModel):
    clause_id: str
    score: float
    standard_text: str
    title: str
    category: str
    source: str


class MatchClauseResponse(BaseModel):
    status: Literal["OK", "NO_RESULT"]
    contract_type: str
    candidates: list[MatchCandidate]
    message: Optional[str] = None


class ReviewContractResponse(BaseModel):
    status: Literal["OK", "EMPTY_DOCUMENT", "CORPUS_UNAVAILABLE", "INVALID_CONFIG", "PIPELINE_ERROR"]
    contract_type: str
    results: list[DeviationResult]
    message: Optional[str] = None


class ClassifyClauseResponse(BaseModel):
    status: Literal["OK", "CORPUS_UNAVAILABLE"]
    contract_type: str
    deviation: Optional[str] = None
    """이탈 판정 결과 (NO_MATCH / EXTRA / CHANGED / NONE). MISSING은 이 도구로 판정 불가(단일조항 입력이라
    "누락 자체"를 발견할 수 없음 — MISSING은 review_contract 에서만 나옴)."""
    confidence: float = 0.0
    matched_standard: Optional[StandardClause] = None
    grounding: list[GroundingLaw] = Field(default_factory=list)
    message: Optional[str] = None


class ListContractTypesResponse(BaseModel):
    contract_types: list[str]


class CategoryInfo(BaseModel):
    value: str
    description: str
    anchors: list[str]


class ListCategoriesResponse(BaseModel):
    categories: list[CategoryInfo]


class ListToxicPatternsResponse(BaseModel):
    patterns: list[str]


class ToxicPatternDetail(BaseModel):
    pattern: str            # ToxicPattern enum 값 (예: "IP_TOTAL_FREE")
    title: str              # 사람이 읽는 대표 제목 (예: "저작권·지식재산권 전부 무상 귀속")
    category: Optional[str] = None
    example_count: int      # 이 패턴에 속한 큐레이션 예시 문구 수


class ListToxicPatternDetailsResponse(BaseModel):
    patterns: list[ToxicPatternDetail]
