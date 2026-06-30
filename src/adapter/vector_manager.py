from chromadb import Collection
import logging
import re
import threading
from typing import List, Dict, Any, Tuple, Optional

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from kiwipiepy import Kiwi

from config import BASE_DIR
from .port import Embedder

# Kiwi 형태소 분석기 초기화 (글로벌 단일 인스턴스)
kiwi = Kiwi()

class VectorManager:
    """
    Chroma Vector DB 및 BM25(Sparse/Lexical) 인덱스를 연동하여 하이브리드 검색을 수행하는 범용 매니저 클래스입니다.
    도메인 의존성(특정 계약 종류, 테이블 구조 등)을 배제하고 컬렉션 단위의 범용적인 문서 벡터 관리를 지원합니다.
    """
    
    def __init__(self, embedder: Embedder):
        self._embedder = embedder
        # 1. 크로마 DB 경로 설정 및 클라이언트 초기화
        self.persist_dir = str(BASE_DIR / "data" / "migration")
        self.settings = Settings(
            is_persistent=True,
            persist_directory=self.persist_dir,
            sqlite_database="chroma_meta.sqlite3"
        )
        self.client = chromadb.PersistentClient(path=self.persist_dir, settings=self.settings)
        
        # 2. BM25 인덱스 캐싱 저장소 (지연 초기화 지원)
        # 키 포맷: (collection_name, filter_tuple)
        self._bm25_indices = {}  # {cache_key: BM25Okapi}
        self._bm25_docs = {}     # {cache_key: List[Dict]}
        self._lock = threading.Lock()

    def get_collection(self, collection_name: str) -> Collection:
        """지정한 이름의 Chroma DB 컬렉션을 가져오거나 새로 생성합니다."""
        return self.client.get_or_create_collection(name=collection_name)

    def _tokenize(self, text: str) -> List[str]:
        """Kiwi 형태소 분석기 및 영문/숫자 정규식을 결합하여 한국어와 영어가 혼재된 텍스트를 토큰화합니다."""
        if not text:
            return []
        
        # 1. Kiwi 형태소 분석기로 토큰화 진행 후 소문자 정규화 (대소문자 구분 없이 매칭되도록 함)
        kiwi_tokens = []
        for token in kiwi.tokenize(text):
            kiwi_tokens.append(token.form.lower())
            
        # 2. 영어 단어 및 숫자가 기호(예: 하이픈 등)로 인해 유실되거나 분리되지 않는 경우를 위해 정규식으로 보완 추출
        eng_num_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        
        # 3. 중복을 방지하며 두 토큰 집합을 결합
        combined_tokens = kiwi_tokens.copy()
        kiwi_set = set(kiwi_tokens)
        for token in eng_num_tokens:
            if token not in kiwi_set:
                combined_tokens.append(token)
                kiwi_set.add(token)
                
        return combined_tokens

    def _make_cache_key(self, collection_name: str, metadata_filter: Optional[Dict[str, Any]] = None) -> Tuple[str, Tuple]:
        """필터 딕셔너리를 해시 가능한 정렬 튜플로 변환하여 캐시 키를 생성합니다."""
        if not metadata_filter:
            return (collection_name, ())
        sorted_filter = tuple(sorted((k, str(v)) for k, v in metadata_filter.items()))
        return (collection_name, sorted_filter)

    def _get_bm25_index(
        self, collection_name: str, metadata_filter: Optional[Dict[str, Any]] = None
    ) -> Tuple[BM25Okapi | None, List[Dict[str, Any]]]:
        """지정된 컬렉션 및 필터 조건에 부합하는 BM25 인덱스를 Chroma DB로부터 로드하여 지연 초기화합니다."""
        cache_key = self._make_cache_key(collection_name, metadata_filter)
        
        with self._lock:
            if cache_key not in self._bm25_indices:
                collection = self.get_collection(collection_name)
                # 컬렉션에서 전체 문서 및 메타데이터 조회
                results = collection.get(
                    where=metadata_filter if metadata_filter else None
                )
                
                if not results or not results.get("ids"):
                    return None, []
                
                # 표준화된 문서 포맷 구성
                docs = []
                ids = results["ids"]
                documents = results["documents"]
                metadatas = results["metadatas"] or [{}] * len(ids)
                
                for doc_id, text, meta in zip(ids, documents, metadatas):
                    doc = {
                        "id": doc_id,
                        "text": text,
                        **(meta or {})
                    }
                    docs.append(doc)
                
                # 형태소 토큰 분석 및 BM25Okapi 빌드
                corpus = [self._tokenize(doc["text"]) for doc in docs]
                self._bm25_indices[cache_key] = BM25Okapi(corpus)
                self._bm25_docs[cache_key] = docs
                
        return self._bm25_indices[cache_key], self._bm25_docs[cache_key]

    def add_documents(
        self, collection_name: str, documents: List[str], ids: List[str], metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """
        지정된 컬렉션에 문서를 일괄 추가하며, BGE-M3 Dense 임베딩을 자동으로 생성하여 적재합니다.
        """
        if not documents:
            return
            
        collection = self.get_collection(collection_name)
        
        # Dense 임베딩 추출
        embeddings = self._embedder.embed_documents(documents)
        
        # Chroma 데이터 저장
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        # 데이터 갱신에 따라 해당 컬렉션 관련 캐싱된 BM25 인덱스 모두 파기
        with self._lock:
            keys_to_remove = [k for k in self._bm25_indices.keys() if k[0] == collection_name]
            for k in keys_to_remove:
                self._bm25_indices.pop(k, None)
                self._bm25_docs.pop(k, None)
    
    def upsert_documents(
        self, collection_name: str, documents: List[str], ids: List[str], metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """
        지정된 컬렉션에 문서를 일괄 추가하며, BGE-M3 Dense 임베딩을 자동으로 생성하여 적재합니다.
        """
        if not documents:
            return
            
        collection = self.get_collection(collection_name)
        
        # Dense 임베딩 추출
        embeddings = self._embedder.embed_documents(documents)
        
        # Chroma 데이터 저장
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        # 데이터 갱신에 따라 해당 컬렉션 관련 캐싱된 BM25 인덱스 모두 파기
        with self._lock:
            keys_to_remove = [k for k in self._bm25_indices.keys() if k[0] == collection_name]
            for k in keys_to_remove:
                self._bm25_indices.pop(k, None)
                self._bm25_docs.pop(k, None)

    def delete_documents(self, collection_name: str, ids: List[str]):
        """지정된 컬렉션에서 ID 매칭 문서를 제거합니다."""
        collection = self.get_collection(collection_name)
        collection.delete(ids=ids)
        
        # 데이터 제거에 따른 캐시 무효화
        with self._lock:
            keys_to_remove = [k for k in self._bm25_indices.keys() if k[0] == collection_name]
            for k in keys_to_remove:
                self._bm25_indices.pop(k, None)
                self._bm25_docs.pop(k, None)

    def dense_search(
        self, collection_name: str, query: str, metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Dense 임베딩 코사인 벡터 비교 기반의 밀도(dense) 조회를 수행합니다."""
        query_vector = self._embedder.embed_query(query)
        collection = self.get_collection(collection_name)
        
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=metadata_filter if metadata_filter else None
        )
        
        scored_docs = []
        if results and results.get("ids"):
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results else [0.0] * len(ids)
            
            for doc_id, text, metadata, dist in zip(ids, documents, metadatas, distances):
                doc = {
                    "id": doc_id,
                    "text": text,
                    "dense_distance": float(dist),
                    **(metadata or {})
                }
                scored_docs.append(doc)
        return scored_docs

    def bm25_search(
        self, collection_name: str, query: str, metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Kiwi 토크나이저를 거친 어휘 유사성 분석(BM25) 기반의 검색을 수행합니다."""
        bm25, docs = self._get_bm25_index(collection_name, metadata_filter)
        if not bm25 or not docs:
            return []
        
        tokenized_query = self._tokenize(query)
        scores = bm25.get_scores(tokenized_query)
        
        scored_docs = []
        for doc, score in zip(docs, scores):
            if score > 0.0:  # 일치하는 토큰이 하나 이상인 경우
                doc_copy = doc.copy()
                doc_copy["bm25_score"] = float(score)
                scored_docs.append(doc_copy)
                
        scored_docs.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored_docs[:top_k]

    def _reciprocal_rank_fusion(self, dense_results: List[Dict], bm25_results: List[Dict], k: int = 60) -> List[Dict]:
        """두 리트리벌 결과 집합의 상호 순위(RRF) 결합 가중치를 매겨 통합 정렬 목록을 생성합니다."""
        scores = {}
        doc_map = {}
        
        for rank, doc in enumerate(dense_results):
            doc_id = doc["id"]
            doc_map[doc_id] = doc
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            
        for rank, doc in enumerate(bm25_results):
            doc_id = doc["id"]
            doc_map[doc_id] = doc
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        fused_docs = []
        for doc_id in sorted_ids:
            doc = doc_map[doc_id].copy()
            doc["fusion_score"] = scores[doc_id]
            fused_docs.append(doc)
            
        return fused_docs

    def hybrid_search(
        self, collection_name: str, query: str, metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Dense 벡터 매칭 및 BM25 키워드 비교를 통합한 하이브리드 RAG 검색을 수행합니다."""
        fetch_k = top_k * 2
        dense_res = self.dense_search(collection_name, query, metadata_filter, top_k=fetch_k)
        bm25_res = self.bm25_search(collection_name, query, metadata_filter, top_k=fetch_k)
        
        fused_results = self._reciprocal_rank_fusion(dense_res, bm25_res)
        return fused_results[:top_k]

    def search(
        self, collection_name: str, query: str, search_type: str = "hybrid", metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """검색 방식 파라미터에 따라 dense, bm25(sparse), hybrid 방식을 범용 매핑해 조회하는 인터페이스입니다."""
        if search_type == "dense":
            return self.dense_search(collection_name, query, metadata_filter, top_k)
        elif search_type in ("bm25", "sparse"):
            return self.bm25_search(collection_name, query, metadata_filter, top_k)
        elif search_type == "hybrid":
            return self.hybrid_search(collection_name, query, metadata_filter, top_k)
        else:
            raise ValueError(f"지원하지 않는 검색 유형입니다: {search_type}")

    def keyword_search(self, collection_name: str, keyword: str, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Chroma의 where_document 필터를 사용해 키워드 텍스트가 포함된 문서를 엄격 발췌합니다."""
        collection = self.get_collection(collection_name)
        
        results = collection.get(
            where=metadata_filter if metadata_filter else None,
            where_document={"$contains": keyword}
        )
        
        docs = []
        if results and results.get("ids"):
            ids = results["ids"]
            documents = results["documents"]
            metadatas = results["metadatas"] or [{}] * len(ids)
            for doc_id, text, metadata in zip(ids, documents, metadatas):
                docs.append({
                    "id": doc_id,
                    "text": text,
                    **(metadata or {})
                })
        return docs

    def regex_search(self, collection_name: str, pattern: str, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """해당 컬렉션 내 필터링 조건에 부합하는 모든 문서를 로드한 뒤 Python re 컴파일 정규식 일치 조회를 실시합니다."""
        collection = self.get_collection(collection_name)
        results = collection.get(
            where=metadata_filter if metadata_filter else None
        )
        
        if not results or not results.get("ids"):
            return []
            
        matched_docs = []
        try:
            regex = re.compile(pattern)
            ids = results["ids"]
            documents = results["documents"]
            metadatas = results["metadatas"] or [{}] * len(ids)
            
            for doc_id, text, metadata in zip(ids, documents, metadatas):
                if regex.search(text):
                    matched_docs.append({
                        "id": doc_id,
                        "text": text,
                        **(metadata or {})
                    })
        except re.error as e:
            logging.error(f"정규식 컴파일 오류: {e}")
            raise
            
        return matched_docs


