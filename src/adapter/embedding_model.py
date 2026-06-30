import threading
from typing import List, Dict, Any
from config import EMBEDDING_MODEL_NAME, RERANKER_MODEL_NAME

from sentence_transformers import SentenceTransformer, CrossEncoder


class Bgem3Embedder:
    """
    dragonkue/BGE-m3-ko 모델을 사용한 임베딩 추출 유틸리티 클래스입니다.
    SentenceTransformer 라이브러리를 사용하며, 싱글톤 패턴 및 지연 로딩(Lazy Loading)을 통해 
    리소스 낭비 및 메모리 중복 적재를 방지합니다.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(Bgem3Embedder, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.model = None
        self._initialized = True

    def _load_model(self):
        """임베딩 모델을 실제로 메모리에 로드합니다. (thread-safe)"""
        if self.model is None:
            with self._lock:
                if self.model is None:
                    # Hugging Face 캐시 경로에 저장된 모델 또는 원격 모델을 로드합니다.
                    # device 설정은 PyTorch가 사용 가능한 GPU가 있으면 자동으로 cuda를 잡고 없으면 cpu를 사용합니다.
                    self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    def embed_query(self, text: str) -> List[float]:
        """
        단일 쿼리 텍스트의 1024차원 고밀도(dense) 임베딩 벡터를 생성합니다.
        """
        embeddings = self.embed_documents([text])
        return embeddings[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        여러 문서 텍스트 목록의 고밀도(dense) 임베딩 벡터들을 생성합니다.
        """
        if not texts:
            return []
        self._load_model()
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]

    def compute_similarity(self, query: str, documents: List[str]) -> List[float]:
        """
        쿼리 텍스트와 여러 문서 텍스트 간의 코사인 유사도를 계산하여 반환합니다.
        (임베딩이 정규화되어 있으므로 단순 내적 합을 통해 계산합니다.)
        """
        if not documents:
            return []
        
        query_emb = self.embed_query(query)
        docs_emb = self.embed_documents(documents)
        
        similarities = []
        for doc_emb in docs_emb:
            sim = sum(q * d for q, d in zip(query_emb, doc_emb))
            similarities.append(float(sim))
            
        return similarities


class BgeReranker:
    """
    dragonkue/bge-reranker-v2-m3-ko 모델을 사용한 리랭킹(재정렬) 유틸리티 클래스입니다.
    SentenceTransformer의 CrossEncoder를 사용하며, 싱글톤 및 지연 로딩을 지원합니다.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(BgeReranker, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.model = None
        self._initialized = True

    def _load_model(self):
        """리랭커 모델을 실제로 메모리에 로드합니다. (thread-safe)"""
        if self.model is None:
            with self._lock:
                if self.model is None:
                    self.model = CrossEncoder(RERANKER_MODEL_NAME)

    def compute_scores(self, query: str, documents: List[str]) -> List[float]:
        """
        쿼리와 각 문서 쌍에 대해 크로스 엔코더 유사도 점수를 계산합니다.
        점수가 높을수록 유사도가 높음을 의미합니다.
        """
        if not documents:
            return []
        self._load_model()
        # CrossEncoder의 입력 포맷인 [(query, doc1), (query, doc2), ...] 생성
        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs)
        # 단일 문서일 경우 float 스칼라가 반환될 수 있으므로 리스트 형태로 변환 보장
        if isinstance(scores, float):
            return [scores]
        return [float(score) for score in scores]

    def rerank(
        self, query: str, items: List[Dict[str, Any]], text_key: str = "text", top_k: int | None = None
    ) -> List[Dict[str, Any]]:
        """
        검색된 문서 목록을 크로스 엔코더를 이용하여 고정밀도로 재정렬합니다.
        각 item 딕셔너리에 'rerank_score' 필드를 추가하고 내림차순 정렬하여 반환합니다.

        Args:
            query (str): 사용자 검색 쿼리 조항
            items (List[Dict]): 재정렬할 문서(조항) 목록
            text_key (str): 각 문서 딕셔너리에서 조항 본문이 저장된 키 이름
            top_k (int, optional): 반환할 상위 항목 수

        Returns:
            List[Dict]: 재정렬된 문서 목록 (유사도 내림차순)
        """
        if not items:
            return []
        
        # 1. 재정렬을 수행할 문서 본문 추출
        documents = [item.get(text_key, "") for item in items]
        
        # 2. 크로스 엔코더 점수 계산
        scores = self.compute_scores(query, documents)
        
        # 3. 각 항목에 점수 부여 및 정렬
        reranked_items = []
        for item, score in zip(items, scores):
            # 원본 데이터 보호를 위해 얕은 복사 수행
            new_item = item.copy()
            new_item["rerank_score"] = score
            reranked_items.append(new_item)
            
        # 점수 기준 내림차순 정렬
        reranked_items.sort(key=lambda x: x["rerank_score"], reverse=True)
        
        if top_k is not None:
            return reranked_items[:top_k]
        return reranked_items


# =================================================================
# 팀원 공용 임베딩/리랭커 객체 (Single Instance)
# 사용법: from adapter import embedder, reranker
# 1. query_vector = embedder.embed_query("제1조...")
# 2. reranked_results = reranker.rerank("제1조...", results)
# =================================================================

embedder = Bgem3Embedder()
reranker = BgeReranker()
