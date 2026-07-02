from chromadb import Collection
import heapq
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Optional

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from kiwipiepy import Kiwi

from config import BASE_DIR
from .port import Embedder

# Kiwi 형태소 분석기 초기화 (글로벌 단일 인스턴스)
kiwi = Kiwi()

# 영문/숫자 보완 추출용 정규식 (반복 컴파일 방지를 위해 모듈 레벨에서 1회 컴파일)
_ENG_NUM_RE = re.compile(r"[a-zA-Z0-9]+")


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
        # 빈 결과(NO_MATCH)도 None 으로 캐싱하여 Chroma 재조회를 방지한다.
        self._bm25_indices = {}  # {cache_key: BM25Okapi | None}
        self._bm25_docs = {}     # {cache_key: List[Dict]}
        self._lock = threading.Lock()

    def get_collection(self, collection_name: str) -> Collection:
        """지정한 이름의 Chroma DB 컬렉션을 가져오거나 새로 생성합니다."""
        return self.client.get_or_create_collection(name=collection_name)

    def _merge_eng_num(self, text: str, kiwi_tokens: List[str]) -> List[str]:
        """Kiwi 토큰에, 기호로 인해 유실/분리된 영문·숫자 토큰을 중복 없이 보완 결합합니다."""
        eng_num_tokens = _ENG_NUM_RE.findall(text.lower())
        if not eng_num_tokens:
            return kiwi_tokens

        combined_tokens = list(kiwi_tokens)
        seen = set(kiwi_tokens)
        for token in eng_num_tokens:
            if token not in seen:
                combined_tokens.append(token)
                seen.add(token)
        return combined_tokens

    def _tokenize(self, text: str) -> List[str]:
        """Kiwi 형태소 분석기 및 영문/숫자 정규식을 결합하여 한국어와 영어가 혼재된 단일 텍스트를 토큰화합니다."""
        if not text:
            return []
        kiwi_tokens = [token.form.lower() for token in kiwi.tokenize(text)]
        return self._merge_eng_num(text, kiwi_tokens)

    def _tokenize_batch(self, texts: List[str]) -> List[List[str]]:
        """여러 텍스트를 Kiwi 배치 토큰화(내부 멀티스레드)로 한 번에 처리합니다. 인덱스 빌드 성능 최적화용."""
        if not texts:
            return []
        # Kiwi 는 Iterable[str] 입력 시 각 텍스트의 토큰 리스트를 순서대로 yield 한다.
        batch_results = kiwi.tokenize(texts)
        corpus = []
        for text, tokens in zip(texts, batch_results):
            kiwi_tokens = [token.form.lower() for token in tokens]
            corpus.append(self._merge_eng_num(text, kiwi_tokens))
        return corpus

    def _make_cache_key(self, collection_name: str, metadata_filter: Optional[Dict[str, Any]] = None) -> Tuple[str, Tuple]:
        """필터 딕셔너리를 해시 가능한 정렬 튜플로 변환하여 캐시 키를 생성합니다."""
        if not metadata_filter:
            return (collection_name, ())
        sorted_filter = tuple(sorted((k, str(v)) for k, v in metadata_filter.items()))
        return (collection_name, sorted_filter)

    def _invalidate_cache(self, collection_name: str) -> None:
        """데이터 갱신/삭제에 따라 해당 컬렉션과 관련된 모든 BM25 캐시를 파기합니다."""
        with self._lock:
            keys_to_remove = [k for k in self._bm25_indices if k[0] == collection_name]
            for k in keys_to_remove:
                self._bm25_indices.pop(k, None)
                self._bm25_docs.pop(k, None)

    def _get_bm25_index(
        self, collection_name: str, metadata_filter: Optional[Dict[str, Any]] = None
    ) -> Tuple[BM25Okapi | None, List[Dict[str, Any]]]:
        """지정된 컬렉션 및 필터 조건에 부합하는 BM25 인덱스를 Chroma DB로부터 로드하여 지연 초기화합니다.

        무거운 빌드 작업(Chroma 조회·토큰화·BM25 생성)은 락 밖에서 수행하여
        다른 컬렉션/필터 조회가 빌드 동안 블로킹되지 않도록 한다(double-checked locking).
        """
        cache_key = self._make_cache_key(collection_name, metadata_filter)

        # 1. 빠른 경로: 이미 캐시된 경우 즉시 반환 (None 도 유효한 NO_MATCH 캐시값)
        with self._lock:
            if cache_key in self._bm25_indices:
                return self._bm25_indices[cache_key], self._bm25_docs[cache_key]

        # 2. 캐시 미스: 락 밖에서 인덱스를 빌드 (다른 키 조회를 막지 않음)
        collection = self.get_collection(collection_name)
        results = collection.get(
            where=metadata_filter if metadata_filter else None
        )

        if not results or not results.get("ids"):
            bm25, docs = None, []
        else:
            ids = results["ids"]
            documents = results["documents"]
            metadatas = results["metadatas"] or [{}] * len(ids)

            docs = [
                {"id": doc_id, "text": text, **(meta or {})}
                for doc_id, text, meta in zip(ids, documents, metadatas)
            ]
            corpus = self._tokenize_batch([doc["text"] for doc in docs])
            bm25 = BM25Okapi(corpus)

        # 3. 캐시에 저장 (다른 스레드가 먼저 빌드했다면 그 결과를 사용)
        with self._lock:
            if cache_key not in self._bm25_indices:
                self._bm25_indices[cache_key] = bm25
                self._bm25_docs[cache_key] = docs
            return self._bm25_indices[cache_key], self._bm25_docs[cache_key]

    def _batch_load(
        self,
        write_fn,
        collection_name: str,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]],
        batch_size: int,
    ) -> None:
        """문서를 배치 단위로 임베딩 후 적재한다.

        임베딩(CPU/GPU 연산)과 Chroma 쓰기(I/O)를 파이프라인화하여, 다음 배치의 임베딩 계산과
        직전 배치의 쓰기가 겹쳐 실행되도록 한다. Chroma 쓰기는 단일 워커로 직렬화되어 안전하다.
        """
        total = len(documents)
        with ThreadPoolExecutor(max_workers=1) as writer:
            pending = None  # 직전 배치의 쓰기 작업 future
            for i in range(0, total, batch_size):
                batch_docs = documents[i: i + batch_size]
                batch_ids = ids[i: i + batch_size]
                batch_metas = metadatas[i: i + batch_size] if metadatas else None

                # Dense 임베딩 추출 (이 사이 직전 배치는 백그라운드에서 쓰기 진행)
                embeddings = self._embedder.embed_documents(batch_docs)

                if pending is not None:
                    pending.result()  # 직전 쓰기 완료 대기 (예외 전파)

                pending = writer.submit(
                    write_fn,
                    ids=batch_ids,
                    embeddings=embeddings,
                    documents=batch_docs,
                    metadatas=batch_metas,
                )
                logging.info(
                    f"[{collection_name}] 적재 진행 중: {min(i + batch_size, total)}/{total}"
                )

            if pending is not None:
                pending.result()  # 마지막 배치 쓰기 완료 대기

    def add_documents(
        self,
        collection_name: str,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        batch_size: int = 128,
    ):
        """지정된 컬렉션에 문서를 배치 단위로 일괄 추가하며, BGE-M3 Dense 임베딩을 자동으로 생성하여 적재합니다."""
        if not documents:
            return

        collection = self.get_collection(collection_name)
        self._batch_load(
            collection.add, collection_name,
            documents, ids, metadatas, batch_size,
        )

        # 데이터 갱신에 따라 해당 컬렉션 관련 캐싱된 BM25 인덱스 모두 파기
        self._invalidate_cache(collection_name)

    def upsert_documents(
        self,
        collection_name: str,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        batch_size: int = 128,
    ):
        """지정된 컬렉션에 문서를 배치 단위로 일괄 업데이트(Upsert)하며, BGE-M3 Dense 임베딩을 자동으로 생성하여 적재합니다."""
        if not documents:
            return

        collection = self.get_collection(collection_name)
        self._batch_load(
            collection.upsert, collection_name,
            documents, ids, metadatas, batch_size,
        )

        # 데이터 갱신에 따라 해당 컬렉션 관련 캐싱된 BM25 인덱스 모두 파기
        self._invalidate_cache(collection_name)

    def delete_documents(self, collection_name: str, ids: List[str]):
        """지정된 컬렉션에서 ID 매칭 문서를 제거합니다."""
        collection = self.get_collection(collection_name)
        collection.delete(ids=ids)

        # 데이터 제거에 따른 캐시 무효화
        self._invalidate_cache(collection_name)

    def _dense_query(
        self, collection: Collection, query_vector: List[float], metadata_filter: Optional[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        """이미 계산된 임베딩 벡터로 Chroma 컬렉션을 조회해 결과 dict 목록을 만듭니다.

        embed_query 호출을 분리해, 배치 검색(search_many)이 임베딩을 한 번만 계산하고 재사용하도록 합니다.
        """
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

    def dense_search(
        self, collection_name: str, vector: List[float], metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """이미 계산된 밀도(dense) 임베딩 벡터로 코사인 벡터 비교 기반 조회를 수행합니다.

        임베딩 계산은 호출부 책임입니다 (VectorManager 는 Embedder 에 의존하지 않음).
        """
        collection = self.get_collection(collection_name)
        return self._dense_query(collection, vector, metadata_filter, top_k)

    def bm25_search(
        self, collection_name: str, query: str, metadata_filter: Optional[Dict[str, Any]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Kiwi 토크나이저를 거친 어휘 유사성 분석(BM25) 기반의 검색을 수행합니다."""
        bm25, docs = self._get_bm25_index(collection_name, metadata_filter)
        if not bm25 or not docs:
            return []

        tokenized_query = self._tokenize(query)
        scores = bm25.get_scores(tokenized_query)

        # 일치 토큰이 하나 이상인(score > 0) 문서 중 상위 top_k 만 선별 (전체 정렬 대신 O(N log k))
        positive = ((idx, score) for idx, score in enumerate(scores) if score > 0.0)
        top = heapq.nlargest(top_k, positive, key=lambda x: x[1])

        scored_docs = []
        for idx, score in top:
            doc_copy = docs[idx].copy()
            doc_copy["bm25_score"] = float(score)
            scored_docs.append(doc_copy)
        return scored_docs

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
        self,
        collection_name: str,
        vector: List[float],
        query: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """이미 계산된 밀도 벡터와 질의 텍스트를 함께 사용해 dense·BM25 결과를 RRF 로 융합합니다.

        Dense·BM25 두 검색은 상호 독립적이므로 병렬 실행하여 지연시간을 max(dense, bm25)로 줄인다.
        임베딩 계산은 호출부 책임입니다 (VectorManager 는 Embedder 에 의존하지 않음).
        """
        fetch_k = top_k * 2
        collection = self.get_collection(collection_name)
        with ThreadPoolExecutor(max_workers=2) as pool:
            dense_future = pool.submit(self._dense_query, collection, vector, metadata_filter, fetch_k)
            bm25_future = pool.submit(self.bm25_search, collection_name, query, metadata_filter, fetch_k)
            dense_res = dense_future.result()
            bm25_res = bm25_future.result()

        fused_results = self._reciprocal_rank_fusion(dense_res, bm25_res)
        return fused_results[:top_k]

    def dense_search_many(
        self,
        collection_name: str,
        vectors: List[List[float]],
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """여러 질의의 밀도 벡터를 한 번에 조회합니다. 벡터는 호출부가 배치로 미리 계산해 둡니다."""
        if not vectors:
            return []
        collection = self.get_collection(collection_name)
        return [self._dense_query(collection, v, metadata_filter, top_k) for v in vectors]

    def bm25_search_many(
        self,
        collection_name: str,
        queries: List[str],
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """여러 질의를 BM25 로 한 번에 검색합니다.

        BM25 인덱스는 (collection, filter)별로 캐시되므로 질의마다 재구축하지 않습니다.
        """
        if not queries:
            return []
        return [self.bm25_search(collection_name, q, metadata_filter, top_k) for q in queries]

    def hybrid_search_many(
        self,
        collection_name: str,
        vectors: List[List[float]],
        queries: List[str],
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """여러 질의를 하이브리드(dense+BM25) 방식으로 한 번에 검색합니다.

        조항별로 hybrid_search 를 개별 호출할 때 발생하는 N회 임베딩 왕복을, 호출부가 vectors 를
        배치로 미리 계산해 넘기게 하여 없앱니다. 반환은 queries 와 1:1 정렬된 결과 목록의 목록입니다.
        """
        if not queries:
            return []

        fetch_k = top_k * 2
        collection = self.get_collection(collection_name)
        fused_per_query = []
        for query, vector in zip(queries, vectors):
            dense_res = self._dense_query(collection, vector, metadata_filter, fetch_k)
            bm25_res = self.bm25_search(collection_name, query, metadata_filter, fetch_k)
            fused = self._reciprocal_rank_fusion(dense_res, bm25_res)
            fused_per_query.append(fused[:top_k])
        return fused_per_query

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
