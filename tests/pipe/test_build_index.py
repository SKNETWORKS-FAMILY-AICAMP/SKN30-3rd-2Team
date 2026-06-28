"""
[작업 규격 · 담당: 팀원 B] pipe.build_index — SQLite → Chroma 인덱스 빌드

구현 대상: src/pipe/build_index.py

    build_standard_index(collection_name="standard_clauses") -> int
        - SQLite standard_clauses 전체를 읽어
        - adapter.embedder 로 임베딩 → adapter.vector.add_documents 로 Chroma 적재
        - 메타데이터에 contract_type·category·clause_id 포함 (검색 시 필터용)
        - 적재한 문서 수 반환

검증: 빌드 후 vector.search 로 시드 조항이 검색되는지 확인하는 통합 테스트.
모델 로딩(bge-m3)·DB 필요로 느리므로, CI 분리를 위해 통합 마커를 답니다.

👉 구현을 시작하면 pytestmark(skip) 줄을 삭제하세요. (먼저 `just migrate` 로 SQLite 준비)
"""
import pytest

pytestmark = pytest.mark.skip(reason="TDD 규격 — 담당: 팀원 B. 구현 시작 시 이 줄 삭제 (통합·느림)")


def test_빌드하면_시드조항_건수만큼_적재():
    from pipe.build_index import build_standard_index
    n = build_standard_index()
    assert n >= 3  # 03_normalized 시드 최소 3건


def test_빌드후_하이브리드_검색으로_조회됨():
    from pipe.build_index import build_standard_index
    from adapter import vector
    build_standard_index()
    results = vector.search("standard_clauses", "저작권의 귀속", search_type="hybrid", top_k=3)
    ids = [r["id"] for r in results]
    assert "sw_freelance-art20" in ids  # 지식재산권의 귀속 조항
