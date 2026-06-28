# 팀원 B — 인덱스 빌드 (`pipe/build_index`)

## 목표
SQLite 의 표준조항을 **bge-m3 로 임베딩해 Chroma 인덱스로 적재**한다. 이걸로 하이브리드
검색이 가능해진다. (형상관리상 Chroma 는 재생성 파생물 — git 에 안 올림)

## 통과할 테스트
- [tests/pipe/test_build_index.py](../../tests/pipe/test_build_index.py) (통합·느림 — 모델 로딩/DB 필요)

## 구현 대상
- [src/pipe/build_index.py](../../src/pipe/build_index.py)
  - `build_standard_index(collection_name="standard_clauses") -> int`
    1. `from adapter import db, vector`
    2. `db.fetch_all("SELECT clause_id, text, contract_type, category, title FROM standard_clauses")`
    3. `vector.add_documents(collection_name, documents=[text...], ids=[clause_id...], metadatas=[{contract_type, category, ...}])`
    4. 적재 건수 반환
- [src/pipe/3.build_index.py](../../src/pipe/3.build_index.py) — CLI (이미 build_standard_index 호출하도록 연결됨)

## 입력 / 출력 계약
- 입력: `standard_clauses` 테이블 (먼저 `just migrate` 실행)
- 출력: Chroma `standard_clauses` 컬렉션. **메타데이터에 `contract_type`·`category`·`clause_id` 필수** (검색 시 필터·식별).
- 검증: `vector.search("standard_clauses", "저작권의 귀속", search_type="hybrid")` 결과에 `sw_freelance-art20` 포함.

## 완료 조건 (DoD)
- [ ] `just migrate && uv run pytest tests/pipe/test_build_index.py` 통과
- [ ] `just build-db` 가 끝까지(migrate → build-index) 에러 없이 동작
- [ ] 적재 건수 로그 출력

## 참고
- [src/adapter/README.md](../../src/adapter/README.md) (`vector.add_documents`, `vector.search`)
- 임베딩은 `adapter.vector` 가 내부에서 자동 수행 (직접 embedder 호출 불필요)
