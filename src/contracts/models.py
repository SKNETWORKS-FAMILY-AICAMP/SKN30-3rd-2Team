from pydantic import BaseModel, Field
from typing import List, Optional
from .enums import ContractType, Category, Deviation, ToxicPattern, EdgeRelation

class Clause(BaseModel):
    """사용자가 업로드한 계약서 등에서 파싱된 개별 조항 모델"""
    idx: int
    """조항의 고유 인덱스 번호 (1부터 시작하는 순서)"""
    num: str
    """조항 번호 (예: "제1조", "제12조")"""
    title: str
    """조항의 대제목/소제목 (예: "기본원칙", "보수의 지급")"""
    text: str
    """조항의 본문 텍스트 전체 내용"""

class StandardClause(BaseModel):
    """데이터베이스(SQLite 및 Chroma)에 저장된 표준 조항 모델"""
    clause_id: str
    """표준 조항 식별 아이디 (예: "sw_freelance-art20")"""
    contract_type: ContractType
    """계약서의 대분류 종류 (예: SW_FREELANCE, SW_EMPLOYMENT 등)"""
    category: Category
    """조항의 성격 분류 카테고리 (예: IP_OWNERSHIP, PAYMENT 등)"""
    title: str
    """표준 조항의 대제목/소제목 (예: "지식재산권의 귀속")"""
    text: str
    """표준 조항의 본문 전체 텍스트"""
    source: str
    """출처 파일명 및 위치 (예: "201231_SW종사자_표준도급계약서.md / 제20조")"""
    version: str
    """표준 계약서의 배포/개정 년도 버전 (예: "2020")"""

class StandardSubChunk(BaseModel):
    """거대 조항의 항·호 단위 서브청크 (coverage 체크 및 Chroma 인덱싱용)"""
    sub_chunk_id: str
    """서브청크 식별 아이디 (예: "sw_freelance-art58-sub01")"""
    parent_clause_id: str
    """소속된 부모 조항의 식별 아이디 (예: "sw_freelance-art58")"""
    sub_chunk_index: int
    """부모 조항 내에서의 항 순서 (0-based)"""
    text: str
    """서브청크의 본문 텍스트"""

class ClauseRelation(BaseModel):
    """[고도화 A] 조항 의존성 그래프의 category 레벨 엣지 (data/03_normalized/clause_relations.json)"""
    source_category: Category
    """영향을 주는 원인 카테고리 (예: IP_OWNERSHIP)"""
    target_category: Category
    """영향을 받는 연동 카테고리 (예: DERIVATIVE_WORK)"""
    relation_type: EdgeRelation
    """조항 간의 의존/연관 관계 유형 (예: RISK_PROPAGATION, DEPENDS_ON)"""

class ToxicPatternRecord(BaseModel):
    """[고도화 B] 양방향 검색용 독소조항 패턴 레코드 (data/03_normalized/toxic_patterns.json)"""
    pattern_id: str
    """독소조항 패턴 식별 아이디 (예: "toxic-ip_total_free-01")"""
    pattern: ToxicPattern
    """부당 계약 패턴 분류 (예: IP_TOTAL_FREE, NONCOMPETE_EXCESS)"""
    category: Optional[Category] = None
    """독소조항이 속하는 계약상의 카테고리 (옵션)"""
    title: str
    """독소조항의 대표 타이틀 제목 (예: "저작권·지식재산권 전부 무상 귀속")"""
    text: str
    """독소조항 판별의 기준이 되는 대표적인 나쁜 예시 문구 텍스트"""

class GroundingLaw(BaseModel):
    """korean-law-mcp 등을 통해 수집한 근거 법령 조문 모델"""
    법령명: str = Field(..., description="법령명 (예: 저작권법, 근로기준법)")
    """법제처 공식 법령명"""
    조번호: str = Field(..., description="조번호 (예: 제5조, 제17조)")
    """법령 내의 조항 번호"""
    본문: str = Field(..., description="법조문 상세 내용")
    """해당 법조문의 구체적인 세부 텍스트"""
    출처: str = Field(..., description="출처 좌표 또는 링크")
    """조문을 인용한 공식 출처 (예: "국가법령정보센터")"""

class DeviationResult(BaseModel):
    """사용자 조항과 표준 조항 간의 검토 결과를 담는 출력 모델"""
    user_clause: str
    """분석 대상이 된 사용자 계약서의 원본 조항 본문"""
    matched_standard: Optional[StandardClause] = None
    """매칭된 표준 계약서 조항 객체 (없는 경우 None)"""
    deviation: Deviation
    """검토 판정 결과 유형 (예: MISSING, EXTRA, CHANGED, NONE, NO_MATCH)"""
    confidence: float
    """매칭 분석에 대한 AI/알고리즘 신뢰도 점수 (0.0 ~ 1.0)"""
    grounding: List[GroundingLaw] = Field(default_factory=list)
    """법리적 근거로 제시할 관련 법령 조문 목록"""
    toxic_patterns: List[ToxicPattern] = Field(default_factory=list)
    """이 조항에서 감지된 불공정 독소조항 패턴 목록"""
    related_risk_clauses: List[str] = Field(default_factory=list)
    """해당 조항 변경으로 인해 함께 검토해야 할 연관 표준 조항 ID 목록"""
