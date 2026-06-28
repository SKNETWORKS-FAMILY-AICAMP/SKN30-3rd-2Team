# src/adapter/ — 외부 세계와의 경계 (어댑터)

DB·임베딩 모델·외부 MCP 등 **바깥 시스템과 통신하는 코드**만 모읍니다. 모두 `contracts/ports.py`의 Protocol을 구현합니다.

> 원칙: 어댑터는 **순수 I/O**만. "이탈 판단" 같은 도메인 로직은 넣지 말 것 → 그건 `core/`. 어댑터는 코어가 시킨 일을 외부에 전달하고 결과를 돌려줄 뿐입니다.

## 팀원 공용 싱글톤 (바로 import 해서 사용)

무거운 리소스(모델 로딩·DB 커넥션)를 매번 새로 만들지 않도록 **단일 인스턴스**로 제공합니다.

```python
from adapter import db, vector, embedder, reranker, kordoc, koreanLaw
```

| 객체 | 클래스 | 대표 사용법 |
| --- | --- | --- |
| `db` | SQLite 매니저 | `db.fetch_all("SELECT * FROM standard_clauses WHERE category=?", "IP_OWNERSHIP")` |
| `vector` | Chroma + BM25 하이브리드 | `vector.search("standard_clauses", query, search_type="hybrid", top_k=5)` |
| `embedder` | bge-m3 임베딩 | `embedder.embed_query("제20조...")`, `embedder.embed_documents([...])` |
| `reranker` | bge-reranker-v2-m3 | `reranker.rerank(query, results, top_k=3)` |
| `kordoc` | 문서 변환 MCP | `kordoc.parse_to_text("a.hwp")`, `kordoc.parse_to_markdown(src, out)` |
| `koreanLaw` | 법령 조회 MCP | `koreanLaw.search_law("저작권 귀속")`, `koreanLaw.cite_check("2020다1234")` |

## 파일
| 파일 | 구현 포트 |
| --- | --- |
| `rdb_manager.py` | (SQLite. thread-local 커넥션) |
| `vector_manager.py` | `Retriever` — dense + BM25(Kiwi) + RRF 융합 |
| `embedding_model.py` | `Embedder` — 임베딩 + 리랭커 (지연 로딩 싱글톤) |
| `kordoc_parser.py` | `Parser` 보조 — HWP/PDF 변환 |
| `korean_law_mcp.py` | `Grounder` 보조 — 법령·판례 조회 |

## 규칙
- 새 어댑터는 반드시 대응 Protocol(`ports.py`)을 따를 것.
- 모델/커넥션은 **모듈 끝의 싱글톤**을 쓰고, 클래스를 직접 `()`로 새로 만들지 말 것.
- 외부 호출 실패 시 빈 값 대신 **명시적 표식/예외**로 알릴 것. (조용한 실패 금지)
