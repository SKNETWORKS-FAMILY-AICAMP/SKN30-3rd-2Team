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
    # 1. SQLite에서 표준조항 전체 조회
    rows = db.fetch_all(
        "SELECT clause_id, text, contract_type, category, title FROM standard_clauses"
    )

    # 빈 테이블이면 조용히 진행하지 않고 명시 예외 (AGENTS.md: 조용한 실패 금지)
    if not rows:
        raise RuntimeError(
            "standard_clauses 테이블이 비어 있습니다. 먼저 `just migrate`를 실행하세요."
        )

    # 2. 새 문서를 먼저 적재 — 실패 시 이전 인덱스가 보존되도록 delete는 나중에
    try:
        vector.upsert_documents(
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
    except Exception as e:
        raise RuntimeError(f"Chroma 적재 실패 — 기존 인덱스는 유지됩니다: {e}") from e

    # 3. 적재 성공 후 구 문서 정리 (include=[] 로 ID만 조회해 메모리 절약)
    existing = vector.get_collection(collection_name).get(include=[])
    old_ids = [id_ for id_ in existing["ids"] if id_ not in {r["clause_id"] for r in rows}]
    if old_ids:
        vector.delete_documents(collection_name, old_ids)

    # 4. 건수 로그 + 반환
    count = len(rows)
    return count


def build_toxic_index(collection_name: str = "toxic_patterns") -> int:
    # 1. SQLite에서 독소조항 패턴 전체 조회
    # ★ 변동 가능: toxic_patterns 테이블에 컬럼이 추가될 경우 SELECT 절을 수정할 것.
    #   현재 컬럼: pattern_id(PK) · pattern(enum) · category · title · text
    rows = db.fetch_all(
        "SELECT pattern_id, pattern, category, title, text FROM toxic_patterns"
    )

    # 빈 테이블이면 조용히 진행하지 않고 명시 예외 (AGENTS.md: 조용한 실패 금지)
    if not rows:
        raise RuntimeError(
            "toxic_patterns 테이블이 비어 있습니다. 먼저 `just migrate`를 실행하세요."
        )

    # 2. 새 문서를 먼저 적재 — 실패 시 이전 인덱스가 보존되도록 delete는 나중에
    try:
        vector.upsert_documents(
            collection_name,
            documents=[r["text"] for r in rows],
            ids=[r["pattern_id"] for r in rows],
            metadatas=[
                {
                    "pattern_id": r["pattern_id"],
                    "pattern":    r["pattern"],
                    "category":   r["category"],
                    "title":      r["title"],
                }
                for r in rows
            ],
        )
    except Exception as e:
        raise RuntimeError(f"Chroma 적재 실패 — 기존 인덱스는 유지됩니다: {e}") from e

    # 3. 적재 성공 후 구 문서 정리 (include=[] 로 ID만 조회해 메모리 절약)
    existing = vector.get_collection(collection_name).get(include=[])
    old_ids = [id_ for id_ in existing["ids"] if id_ not in {r["pattern_id"] for r in rows}]
    if old_ids:
        vector.delete_documents(collection_name, old_ids)

    # 4. 건수 로그 + 반환
    count = len(rows)
    return count

def build_sub_chunk_index(collection_name: str = "standard_sub_chunks") -> int:
    import re
    # 1. SQLite에서 표준조항 전체 조회
    rows = db.fetch_all(
        "SELECT clause_id, text, contract_type, category, title FROM standard_clauses"
    )
    if not rows:
        return 0

    sub_chunks = []
    
    # 2. 거대 조항 서브청킹 로직
    for r in rows:
        clause_id = r["clause_id"]
        text = r["text"]
        
        symbols = re.findall(r"[①-⑳]", text)
        nums = re.findall(r"^[0-9]+\.", text, flags=re.MULTILINE)
        
        # 500자 초과 OR 기호 3개 이상이면 쪼개기 (분할 조건)
        if len(text) > 500 or (len(symbols) + len(nums)) >= 3:
            parts = re.split(r"(^[①-⑳]|^[0-9]+\.)", text, flags=re.MULTILINE)
            
            current_chunk = parts[0].strip()
            idx = 0
            
            if current_chunk:
                sub_chunks.append({
                    "sub_chunk_id": f"{clause_id}-sub{idx:02d}",
                    "parent_clause_id": clause_id,
                    "sub_chunk_index": idx,
                    "text": current_chunk
                })
                idx += 1
                
            for i in range(1, len(parts), 2):
                symbol = parts[i]
                content = parts[i+1] if i+1 < len(parts) else ""
                chunk_text = (symbol + content).strip()
                if chunk_text:
                    sub_chunks.append({
                        "sub_chunk_id": f"{clause_id}-sub{idx:02d}",
                        "parent_clause_id": clause_id,
                        "sub_chunk_index": idx,
                        "text": chunk_text
                    })
                    idx += 1
        else:
            # 쪼개지 않고 조 전체를 1청크로 유지
            sub_chunks.append({
                "sub_chunk_id": f"{clause_id}-sub00",
                "parent_clause_id": clause_id,
                "sub_chunk_index": 0,
                "text": text
            })

    # 3. SQLite 적재 (standard_sub_chunks)
    db.execute_query("DELETE FROM standard_sub_chunks")
    insert_query = "INSERT INTO standard_sub_chunks (sub_chunk_id, parent_clause_id, sub_chunk_index, text) VALUES (?, ?, ?, ?)"
    params_list = [(s["sub_chunk_id"], s["parent_clause_id"], s["sub_chunk_index"], s["text"]) for s in sub_chunks]
    db.execute_many(insert_query, params_list)

    # 4. Chroma 적재 (upsert)
    try:
        vector.upsert_documents(
            collection_name,
            documents=[s["text"] for s in sub_chunks],
            ids=[s["sub_chunk_id"] for s in sub_chunks],
            metadatas=[
                {
                    "parent_clause_id": s["parent_clause_id"],
                    "sub_chunk_index": s["sub_chunk_index"],
                }
                for s in sub_chunks
            ],
        )
    except Exception as e:
        raise RuntimeError(f"Chroma 적재 실패 (sub_chunks): {e}") from e

    existing = vector.get_collection(collection_name).get(include=[])
    old_ids = [id_ for id_ in existing["ids"] if id_ not in {s["sub_chunk_id"] for s in sub_chunks}]
    if old_ids:
        vector.delete_documents(collection_name, old_ids)

    return len(sub_chunks)

if __name__ == "__main__":
    n = build_standard_index()
    print(f"[OK] Chroma 인덱스 적재 완료 (standard_clauses): {n}건")
    
    n_sub = build_sub_chunk_index()
    print(f"[OK] Chroma 인덱스 적재 완료 (standard_sub_chunks): {n_sub}건")
