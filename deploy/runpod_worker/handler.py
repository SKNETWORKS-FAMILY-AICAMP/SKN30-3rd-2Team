"""RunPod 서버리스 커스텀 워커 — 임베딩(dragonkue/BGE-m3-ko) + 리랭킹(dragonkue/bge-reranker-v2-m3-ko).

src/adapter/embedding_model.py 의 embedder·reranker 싱글톤을 그대로 재사용한다(Dockerfile이 빌드 시
복사). job input/output 스키마는 src/adapter/api_embedding_model.py(ApiEmbedder·ApiReranker)의
호출 규격과 정확히 맞춰져 있어, 해당 어댑터 코드는 무수정으로 이 워커를 호출할 수 있다.

worker-infinity-embedding(RunPod Hub) 대신 자체 구현을 쓰는 이유: 그 이미지는 rerank 응답을
JSON 직렬화하지 못하는 미해결 버그가 있다(runpod-workers/worker-infinity-embedding#37, #29).
"""
from typing import Any, Dict

import runpod

from embedding_model import embedder, reranker


def _handle_embedding(job_input: Dict[str, Any]) -> Dict[str, Any]:
    texts = job_input["input"]
    if isinstance(texts, str):
        texts = [texts]
    embeddings = embedder.embed_documents(texts)
    return {
        "object": "list",
        "model": job_input.get("model"),
        "data": [
            {"object": "embedding", "embedding": emb, "index": i}
            for i, emb in enumerate(embeddings)
        ],
    }


def _handle_rerank(job_input: Dict[str, Any]) -> Dict[str, Any]:
    query = job_input["query"]
    docs = job_input["docs"]
    scores = reranker.compute_scores(query, docs)
    if job_input.get("return_docs"):
        return {"docs": docs, "scores": scores}
    return {"scores": scores}


def _handle_rerank_many(job_input: Dict[str, Any]) -> Dict[str, Any]:
    queries = job_input["queries"]
    docs_per_query = job_input["docs_per_query"]
    scores_per_query = reranker.compute_scores_many(queries, docs_per_query)
    return {"scores_per_query": scores_per_query}


def _module_device(module: Any) -> str:
    """nn.Module이 실제로 어느 device(cpu/cuda)에 올라가 있는지 확인한다.

    sentence-transformers 버전에 따라 CrossEncoder가 자신이 직접 nn.Module이거나
    내부 model 속성에 감싸져 있을 수 있어 둘 다 시도한다.
    """
    try:
        return str(next(module.parameters()).device)
    except AttributeError:
        return str(next(module.model.parameters()).device)


def _handle_debug(_job_input: Dict[str, Any]) -> Dict[str, Any]:
    """GPU 실사용 여부 진단용 — 강제로 한 번 로드·추론시켜 실제 device를 확인한다."""
    import torch

    embedder.embed_query("디버그")
    reranker.compute_scores("디버그", ["디버그"])

    return {
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "embed_model_device": _module_device(embedder.model),
        "rerank_model_device": _module_device(reranker.model),
    }


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    job_input = job["input"]
    if job_input.get("debug"):
        return _handle_debug(job_input)
    if "queries" in job_input:
        return _handle_rerank_many(job_input)
    if "query" in job_input:
        return _handle_rerank(job_input)
    if "input" in job_input:
        return _handle_embedding(job_input)
    raise ValueError(f"지원하지 않는 job input 형식입니다: {job_input}")


runpod.serverless.start({"handler": handler})
