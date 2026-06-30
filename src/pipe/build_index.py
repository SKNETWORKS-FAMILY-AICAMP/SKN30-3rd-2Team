"""
[담당: 팀원 B] SQLite → Chroma 인덱스 빌드 로직 (import 가능 모듈)

규격(통과해야 할 테스트): tests/pipe/test_build_index.py
참고 문서: src/pipe/README.md, src/adapter/README.md

CLI 실행부는 3.build_index.py 가 이 함수를 호출합니다. (먼저 `just migrate` 로 SQLite 준비)
"""

import sys, logging
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapter import db, vector


def _build_index_from_db(
    table_name: str,
    collection_name: str,
    id_column: str,
    metadata_columns: List[str],
    text_column: str = "text",
) -> int:
    """SQLite 테이블 데이터를 조회하여 Chroma 벡터 데이터베이스에 적재 및 동기화하는 공통 함수.

    Args:
        table_name (str): RDB SQLite 테이블 이름
        collection_name (str): Chroma 컬렉션 이름
        id_column (str): ID로 사용할 컬럼명 (PK)
        metadata_columns (List[str]): Chroma 메타데이터에 포함시킬 컬럼 목록
        text_column (str, optional): 텍스트 임베딩 대상 컬럼명. Defaults to "text".

    Returns:
        int: 적재 및 동기화된 문서 건수
    """
    # 1. SQLite에서 데이터 조회
    query_columns = [id_column, text_column] + metadata_columns
    # 중복 컬럼 제거 (순서 보존)
    unique_columns = []
    for col in query_columns:
        if col not in unique_columns:
            unique_columns.append(col)

    query = f"SELECT {', '.join(unique_columns)} FROM {table_name}"
    rows = db.fetch_all(query)

    # 빈 테이블이면 조용히 진행하지 않고 명시 예외 (AGENTS.md: 조용한 실패 금지)
    if not rows:
        raise RuntimeError(
            f"{table_name} 테이블이 비어 있습니다. 먼저 `just migrate`를 실행하세요."
        )

    # 2. 오프라인 코퍼스 빌드 작업이므로 기존 Chroma 컬렉션을 완전히 삭제하고 초기화하여 깨끗한 상태로 재적재합니다.
    try:
        vector.client.delete_collection(collection_name)
    except Exception:
        pass

    # 3. 새 문서 적재
    try:
        logging.info(f"[{collection_name}] 적재 시작 {len(rows)}건")
        vector.upsert_documents(
            collection_name,
            documents=[r[text_column] for r in rows],
            ids=[r[id_column] for r in rows],
            metadatas=[
                {col: r[col] for col in metadata_columns}
                for r in rows
            ],
        )
    except Exception as e:
        raise RuntimeError(f"Chroma 적재 실패 ({collection_name}): {e}") from e

    return len(rows)


def build_standard_index(collection_name: str = "standard_clauses") -> int:
    """standard_clauses 테이블의 조항들을 Chroma 컬렉션에 빌드합니다."""
    return _build_index_from_db(
        table_name="standard_clauses",
        collection_name=collection_name,
        id_column="clause_id",
        metadata_columns=["clause_id", "contract_type", "category", "title"],
    )


def build_toxic_index(collection_name: str = "toxic_patterns") -> int:
    """toxic_patterns 테이블의 독소조항 패턴들을 Chroma 컬렉션에 빌드합니다."""
    return _build_index_from_db(
        table_name="toxic_patterns",
        collection_name=collection_name,
        id_column="pattern_id",
        metadata_columns=["pattern_id", "pattern", "category", "title"],
    )


def build_sub_chunk_index(collection_name: str = "standard_sub_chunks") -> int:
    """standard_sub_chunks 테이블의 서브청크들을 Chroma 컬렉션에 빌드합니다."""
    return _build_index_from_db(
        table_name="standard_sub_chunks",
        collection_name=collection_name,
        id_column="sub_chunk_id",
        metadata_columns=["parent_clause_id", "sub_chunk_index"],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = build_standard_index()
    logging.info(f"[OK] Chroma 인덱스 적재 완료 (standard_clauses): {n}건")

    n_sub = build_sub_chunk_index()
    logging.info(f"[OK] Chroma 인덱스 적재 완료 (standard_sub_chunks): {n_sub}건")
