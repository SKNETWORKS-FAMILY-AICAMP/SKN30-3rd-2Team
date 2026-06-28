"""
[담당: 팀원 B] SQLite → Chroma 인덱스 빌드 로직 (import 가능 모듈)

규격(통과해야 할 테스트): tests/pipe/test_build_index.py
참고 문서: src/pipe/README.md, src/adapter/README.md

CLI 실행부는 3.build_index.py 가 이 함수를 호출합니다. (먼저 `just migrate` 로 SQLite 준비)
"""


def build_standard_index(collection_name: str = "standard_clauses") -> int:
    """
    SQLite standard_clauses 전체를 읽어 bge-m3 임베딩 후 Chroma 컬렉션에 적재합니다.

    - 메타데이터에 contract_type·category·clause_id 포함(검색 시 필터·식별용).
    - 반환: 적재한 문서 수.
    """
    # TODO(팀원 B): 아래 순서로 구현
    #   1. from adapter import db, vector
    #   2. rows = db.fetch_all("SELECT clause_id, text, contract_type, category, title FROM standard_clauses")
    #   3. vector.add_documents(collection_name, documents=[...text...], ids=[...clause_id...], metadatas=[...])
    #   4. return len(rows)
    raise NotImplementedError("담당: 팀원 B — tests/pipe/test_build_index.py 를 통과시키세요.")

if __name__ == "__main__":
    n = build_standard_index()
    print(f"✅ Chroma 인덱스 적재 완료: {n}건")
