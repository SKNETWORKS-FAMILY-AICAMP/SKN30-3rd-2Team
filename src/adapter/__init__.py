from config import app_env
from .rdb_manager import db
from .vector_manager import VectorManager
from .kordoc import kordoc
from .korean_law_mcp import koreanLaw
from .markdown_splitter import splitter

if app_env == "local":
    from .embedding_model import embedder, reranker
else:
    from .api_embedding_model import api_embedder as embedder, api_reranker as reranker  # type: ignore[assignment]

# VectorManager는 Embedder를 주입받아 조립 — 테스트 시 mock_embedder로 교체 가능
vector = VectorManager(embedder=embedder)

__all__ = ['db', 'embedder', 'reranker', 'vector', 'kordoc', 'koreanLaw', 'splitter']