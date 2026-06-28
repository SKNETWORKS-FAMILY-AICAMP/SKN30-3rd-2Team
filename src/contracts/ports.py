from typing import Protocol, List, Dict, Any, Optional
from .models import Clause, StandardClause, GroundingLaw, DeviationResult
from .enums import ContractType, Category

class Parser(Protocol):
    """계약서 파일을 분석하여 조항(Clause) 리스트로 정규 분해하는 포트 인터페이스"""
    def parse(self, file_path: str) -> List[Clause]:
        """계약서 원본 파일(HWP/PDF 등)을 마크다운으로 추출하고 조항 단위로 정밀 분해하여 반환합니다.
        
        Args:
            file_path: 분석 대상 파일의 절대 경로
            
        Returns:
            분해된 개별 조항(Clause) 객체들의 목록
        """
        ...

class Embedder(Protocol):
    """밀도/희소 텍스트 임베딩 계산 및 크로스 인코더 재정렬을 수행하는 포트 인터페이스"""
    def embed_query(self, text: str) -> List[float]:
        """단일 쿼리(질의) 텍스트를 1024차원의 밀도(dense) 임베딩 벡터로 변환합니다.
        
        Args:
            text: 임베딩 처리할 단일 텍스트 문구
            
        Returns:
            1024차원의 부동 소수점 임베딩 벡터 리스트
        """
        ...
        
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """여러 문서 텍스트 목록을 1024차원의 밀도(dense) 임베딩 벡터 목록으로 일괄 변환합니다.
        
        Args:
            texts: 임베딩 처리할 여러 문서들의 텍스트 목록
            
        Returns:
            각 문서의 1024차원 임베딩 벡터를 담은 2차원 리스트
        """
        ...
        
    def compute_similarity(self, query: str, documents: List[str]) -> List[float]:
        """질의 텍스트와 여러 문서들 간의 코사인 유사도(Cosine Similarity)를 계산해 반환합니다.
        
        Args:
            query: 기준이 되는 질의(쿼리) 텍스트
            documents: 유사도를 비교할 대상 문서들의 텍스트 목록
            
        Returns:
            각 문서별 유사도 매칭 점수를 담은 실수 리스트
        """
        ...

class Retriever(Protocol):
    """벡터 데이터베이스(ChromaDB) 및 어휘 색인(BM25)을 통해 유사 조항을 검색하는 포트 인터페이스"""
    def search(
        self, collection_name: str, query: str, search_type: str = "hybrid", metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """색인된 데이터베이스에서 특정 질의와 의미적/키워드적으로 가장 잘 매칭되는 조항들을 검색합니다.
        
        Args:
            collection_name: 검색 대상 데이터베이스 컬렉션 이름 (예: "standard_clauses")
            query: 검색을 유도할 질의(쿼리) 텍스트
            search_type: 검색 방식 (예: "hybrid", "dense", "bm25")
            metadata_filter: 특정 계약 유형이나 버전을 필터링할 메타데이터 조건 (옵션)
            top_k: 검색해서 가져올 최상위 후보군의 갯수
            
        Returns:
            유사도 점수와 식별 메타데이터를 포함한 검색 결과 사전(Dict) 목록
        """
        ...

class Grounder(Protocol):
    """카테고리 분류나 본문 텍스트에 기반하여 관련 근거 법조문을 수집하는 포트 인터페이스"""
    def get_grounding(self, category: Category) -> List[GroundingLaw]:
        """주어진 조항 분류 카테고리에 대한 표준적인 대한민국 관련 법령 근거를 수집합니다.
        
        Args:
            category: 분석 중인 이탈 조항의 성격 대분류 카테고리
            
        Returns:
            매칭되는 구체적인 근거 법조문(GroundingLaw) 목록
        """
        ...
        
    def query_law(self, clause_text: str) -> List[GroundingLaw]:
        """사용자 조항 본문 텍스트의 맥락을 분석하여 연관된 법조문을 동적으로 검색 및 수집합니다.
        
        Args:
            clause_text: 분석 및 대조의 대상이 되는 사용자의 실제 조항 내용
            
        Returns:
            검색 결과로 도출된 연관 근거 법조문(GroundingLaw) 목록
        """
        ...

class Graph(Protocol):
    """조항 간의 의존성 관계 및 위험 전파 경로를 관리하고 질의하는 포트 인터페이스"""
    def get_related_risks(self, clause_id: str) -> List[str]:
        """특정 조항에 변경이나 누락 이탈이 생겼을 때, 연쇄 검토해야 하는 타 조항들의 ID 목록을 추적합니다.
        
        Args:
            clause_id: 이탈이 발생한 기준 조항 ID
            
        Returns:
            연계 위험으로 판단되는 관련 표준 조항 ID 목록
        """
        ...
        
    def add_relation(self, source_category: Category, target_category: Category, relation_type: str) -> None:
        """조항 카테고리 간의 새로운 연관/의존 관계 규칙을 그래프 구조에 추가합니다.
        
        Args:
            source_category: 원인 조항 카테고리
            target_category: 영향을 받는 대상 조항 카테고리
            relation_type: 관계의 물리적 유형 (예: "RISK_PROPAGATION")
        """
        ...
