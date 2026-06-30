from typing import Literal, Optional
from pydantic import BaseModel
from contracts.models import Clause, GroundingLaw, DeviationResult


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
