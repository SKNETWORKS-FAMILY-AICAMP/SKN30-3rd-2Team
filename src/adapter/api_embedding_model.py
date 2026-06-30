"""
RunPod serverless 엔드포인트를 호출하는 운영용 임베더·리랭커 구현체.

로컬에서는 embedding_model.py(로컬 모델)를 사용하고,
app_env != "local" 일 때 adapter/__init__.py 가 이 모듈의 인스턴스를 선택한다.

엔드포인트 규격: POST https://api.runpod.ai/v2/<ENDPOINT_ID>/runsync
응답 외피: { "id": "...", "status": "COMPLETED", "output": { <실제 페이로드> } }
"""
import logging
from typing import Any, Dict, List

import requests

from config import EMBEDDING_MODEL_NAME, RERANKER_MODEL_NAME, RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID

_TIMEOUT = 60  # RunPod cold-start 고려


def _base_url() -> str:
    if not RUNPOD_ENDPOINT_ID:
        raise RuntimeError("RUNPOD_ENDPOINT_ID 환경변수가 설정되지 않았습니다.")
    return f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}"


def _headers() -> Dict[str, str]:
    if not RUNPOD_API_KEY:
        raise RuntimeError("RUNPOD_API_KEY 환경변수가 설정되지 않았습니다.")
    return {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json",
    }


def _call_runsync(payload: Dict[str, Any]) -> Dict[str, Any]:
    """RunPod /runsync 호출 후 output 페이로드를 꺼내 반환한다."""
    url = f"{_base_url()}/runsync"
    try:
        resp = requests.post(url, json={"input": payload}, headers=_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"RunPod API 호출 실패: {e}")
        raise RuntimeError(f"RunPod API 호출 실패: {e}") from e

    body = resp.json()
    if body.get("status") != "COMPLETED":
        raise RuntimeError(f"RunPod 작업 미완료: status={body.get('status')}, body={body}")

    output = body.get("output")
    if output is None:
        raise RuntimeError(f"RunPod 응답에 output 키가 없습니다: {body}")
    return output


class ApiEmbedder:
    """RunPod OpenAI-compatible 임베딩 엔드포인트를 호출하는 운영용 Embedder 구현체."""

    def __init__(self, model: str = EMBEDDING_MODEL_NAME):
        self._model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """문서 목록을 일괄 임베딩한다. 빈 목록이면 빈 리스트 반환."""
        if not texts:
            return []

        output = _call_runsync({"model": self._model, "input": texts})

        # output: { "object": "list", "data": [ { "embedding": [...], "index": 0 }, ... ] }
        data: List[Dict[str, Any]] = output.get("data", [])
        if not data:
            raise RuntimeError(f"RunPod 임베딩 응답에 data가 비어 있습니다: {output}")

        # index 순서대로 정렬하여 입력 순서와 일치시킴
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    def embed_query(self, text: str) -> List[float]:
        """단일 쿼리 텍스트를 임베딩한다."""
        return self.embed_documents([text])[0]

    def compute_similarity(self, query: str, documents: List[str]) -> List[float]:
        """쿼리와 각 문서 간 코사인 유사도를 계산한다. (정규화 임베딩 → 내적)"""
        if not documents:
            return []

        query_emb = self.embed_query(query)
        docs_emb = self.embed_documents(documents)

        return [
            float(sum(q * d for q, d in zip(query_emb, doc_emb)))
            for doc_emb in docs_emb
        ]


class ApiReranker:
    """RunPod rerank 엔드포인트를 호출하는 운영용 Reranker 구현체."""

    def __init__(self, model: str = RERANKER_MODEL_NAME):
        self._model = model

    def compute_scores(self, query: str, documents: List[str]) -> List[float]:
        """쿼리와 각 문서 쌍의 크로스 인코더 점수를 반환한다."""
        if not documents:
            return []

        output = _call_runsync({
            "model": self._model,
            "query": query,
            "docs": documents,
            "return_docs": False,
        })

        # output: { "scores": [0.9, 0.1, ...] }  (return_docs=false 일 때)
        scores = output.get("scores")
        if scores is None:
            raise RuntimeError(f"RunPod rerank 응답에 scores 키가 없습니다: {output}")
        return [float(s) for s in scores]

    def rerank(
        self,
        query: str,
        items: List[Dict[str, Any]],
        text_key: str = "text",
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """items를 크로스 인코더 점수 기준 내림차순으로 재정렬하여 반환한다."""
        if not items:
            return []

        documents = [item.get(text_key, "") for item in items]
        scores = self.compute_scores(query, documents)

        reranked = []
        for item, score in zip(items, scores):
            new_item = item.copy()
            new_item["rerank_score"] = score
            reranked.append(new_item)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k] if top_k is not None else reranked


# =================================================================
# 운영용 공용 인스턴스
# adapter/__init__.py 가 app_env 에 따라 이 인스턴스 또는
# embedding_model.py 의 인스턴스를 선택해 노출한다.
# =================================================================
api_embedder = ApiEmbedder()
api_reranker = ApiReranker()
