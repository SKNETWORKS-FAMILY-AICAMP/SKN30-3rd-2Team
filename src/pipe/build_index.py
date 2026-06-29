"""
[담당: 팀원 B] SQLite → Chroma 인덱스 빌드 로직 (import 가능 모듈)

규격(통과해야 할 테스트): tests/pipe/test_build_index.py
참고 문서: src/pipe/README.md, src/adapter/README.md

CLI 실행부는 3.build_index.py 가 이 함수를 호출합니다. (먼저 `just migrate` 로 SQLite 준비)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapter import db, vector

def build_standard_index(collection_name: str = "standard_clauses") -> int:
    # 재빌드 시 중복 ID 오류 방지: 기존 문서를 먼저 삭제
    existing = vector.get_collection(collection_name).get()
    if existing["ids"]:
        vector.delete_documents(collection_name, existing["ids"])

    # 1. SQLite에서 표준조항 전체 조회
    rows = db.fetch_all(
        "SELECT clause_id, text, contract_type, category, title FROM standard_clauses"
    )

    # 2. Chroma에 적재
    vector.add_documents(
        collection_name,
        documents=[r["text"] for r in rows],
        ids=[r["clause_id"] for r in rows],
        metadatas=[
            {
                "clause_id": r["clause_id"],
                "contract_type": r["contract_type"],
                "category": r["category"],
                "title": r["title"],
            }
            for r in rows
        ],
    )

    # 3. 건수 로그 + 반환
    count = len(rows)
    return count

if __name__ == "__main__":
    n = build_standard_index()
    print(f"✅ Chroma 인덱스 적재 완료: {n}건")