from typing import Protocol, List, Dict, Any, Optional


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
        self,
        collection_name: str,
        query: str,
        search_type: str = "hybrid",
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
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

    def search_many(
        self,
        collection_name: str,
        queries: List[str],
        search_type: str = "hybrid",
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """여러 질의를 한 번에 검색합니다. dense 임베딩을 배치로 계산해 모델 왕복(N회→1회)을 줄입니다.

        조항 단위 검토 루프에서 조항마다 search 를 개별 호출하면 임베딩 왕복이 N번 직렬화됩니다.
        이 메서드는 임베딩을 배치화하여 지연시간을 낮춥니다. 반환 리스트는 queries 와 1:1 정렬됩니다.

        Args:
            collection_name: 검색 대상 컬렉션 이름
            queries: 검색할 질의 텍스트 목록
            search_type: 검색 방식 ("hybrid", "dense", "bm25")
            metadata_filter: 메타데이터 필터 조건 (옵션)
            top_k: 각 질의당 반환할 최상위 후보 갯수

        Returns:
            queries 와 같은 순서로 정렬된, 질의별 검색 결과 목록의 목록
        """
        ...


class Reranker(Protocol):
    """크로스 인코더 기반 재정렬(rerank)을 수행하는 포트 인터페이스"""

    def compute_scores(self, query: str, documents: List[str]) -> List[float]:
        """쿼리와 각 문서 쌍에 대해 크로스 인코더 유사도 점수를 계산합니다.

        Args:
            query: 기준 쿼리 텍스트
            documents: 점수를 매길 문서 목록

        Returns:
            각 문서별 유사도 점수 리스트 (높을수록 더 유사)
        """
        ...

    def compute_scores_many(
        self, queries: List[str], docs_per_query: List[List[str]]
    ) -> List[List[float]]:
        """여러 질의의 (질의, 문서) 쌍 점수를 한 번에 계산합니다(정렬 없음, 입력 순서 보존).

        질의별 compute_scores 를 N번 부르는 대신 pair 를 flatten 해 단일 forward/네트워크
        호출로 접습니다(rerank_many 와 동일한 배치화 취지, 단 정렬·top_k 절단은 없음).

        Args:
            queries: 기준 쿼리 텍스트 목록
            docs_per_query: 각 쿼리에 대응하는 문서 목록의 목록 (queries 와 1:1)

        Returns:
            쿼리별 점수 리스트의 리스트. result[i] 는 queries[i] 와 docs_per_query[i]
            각 문서의 점수이며, queries 와 1:1 로 순서가 보존됩니다.
        """
        ...

    def rerank(
        self,
        query: str,
        items: List[Dict[str, Any]],
        text_key: str = "text",
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """검색된 문서 목록을 크로스 인코더를 이용하여 고정밀도로 재정렬합니다.

        Args:
            query: 사용자 검색 쿼리 조항
            items: 재정렬할 문서(조항) 목록
            text_key: 각 문서 딕셔너리에서 본문이 저장된 키 이름
            top_k: 반환할 상위 항목 수 (None이면 전체)

        Returns:
            rerank_score 필드가 추가된 재정렬 문서 목록 (내림차순)
        """
        ...

    def rerank_many(
        self,
        queries: List[str],
        items_per_query: List[List[Dict[str, Any]]],
        text_key: str = "text",
        top_k: int | None = None,
    ) -> List[List[Dict[str, Any]]]:
        """여러 질의의 재정렬을 한 번에 처리합니다(질의별 rerank 를 배치화).

        cross-encoder 는 (질의, 문서) 쌍 단위로 점수를 내므로 질의별 호출이 자연스럽지만,
        모든 질의의 쌍을 펼쳐(flatten) 단일 forward pass 로 채점하면 모델 배치를 가득 채워
        호출 오버헤드를 줄일 수 있습니다. 각 쌍은 독립 채점되므로 점수는 질의별 rerank 와 동일합니다.

        Args:
            queries: 질의 텍스트 목록
            items_per_query: 질의와 1:1 정렬된, 질의별 재정렬 대상 문서 목록의 목록
            text_key: 각 문서 dict 에서 본문이 저장된 키 이름
            top_k: 질의별 반환 상위 항목 수 (None이면 전체)

        Returns:
            queries 와 1:1 정렬된, 질의별 재정렬 결과(rerank_score 부여·내림차순) 목록의 목록
        """
        ...


class Database(Protocol):
    """SQLite 데이터베이스 쿼리 실행 및 조회를 담당하는 포트 인터페이스"""

    def execute_query(
        self,
        query: str,
        params: tuple | list | dict | str | int | None = None,
    ) -> bool:
        """데이터 변경(INSERT, UPDATE, DELETE) 쿼리를 실행합니다.

        Args:
            query: 실행할 SQL 쿼리 문자열
            params: 쿼리 파라미터

        Returns:
            성공 시 True
        """
        ...

    def execute_many(
        self,
        query: str,
        params_list: list[tuple],
        chunk_size: int = 1000,
    ) -> int:
        """다량의 데이터를 배치로 INSERT/UPDATE합니다.

        Args:
            query: 실행할 쿼리 템플릿
            params_list: 각 행에 해당하는 파라미터 튜플 리스트
            chunk_size: 한 번에 처리할 행 수

        Returns:
            성공적으로 삽입된 총 행 수
        """
        ...

    def fetch_all(
        self,
        query: str,
        params: tuple | list | dict | str | int | None = None,
    ) -> list:
        """SELECT 결과 전체를 딕셔너리 리스트로 반환합니다.

        Args:
            query: 실행할 SELECT 쿼리
            params: 쿼리 파라미터

        Returns:
            각 행을 딕셔너리로 변환한 리스트
        """
        ...

    def fetch_one(
        self,
        query: str,
        params: tuple | list | dict | str | int | None = None,
    ) -> dict | None:
        """SELECT 결과 단일 행을 딕셔너리로 반환합니다.

        Args:
            query: 실행할 SELECT 쿼리
            params: 쿼리 파라미터

        Returns:
            단일 행 딕셔너리, 결과 없으면 None
        """
        ...
