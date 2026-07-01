"""adapter.embedding_model._scatter_reranked 규격 테스트 — rerank_many 의 flatten/scatter 순수 로직.

모델 없이 검증 가능한 부분(소유 질의 매핑·질의별 내림차순 정렬·top_k 절단·빈 그룹 보존)만 고정한다.
실제 model.predict 채점은 rerank 와 동일하므로 여기서 다루지 않는다.
"""
from adapter.embedding_model import _scatter_reranked


def test_소유질의별로_되담고_점수부여():
    flat_items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    flat_owner = [0, 1, 0]                 # a·c → 질의0, b → 질의1
    scores = [0.2, 0.9, 0.8]
    result = _scatter_reranked(2, flat_items, flat_owner, scores, top_k=None)

    assert [i["id"] for i in result[0]] == ["c", "a"]   # 질의0: 0.8 > 0.2 내림차순
    assert [i["id"] for i in result[1]] == ["b"]
    assert result[0][0]["rerank_score"] == 0.8


def test_top_k_절단은_질의별로():
    flat_items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    flat_owner = [0, 0, 0]
    scores = [0.1, 0.9, 0.5]
    result = _scatter_reranked(1, flat_items, flat_owner, scores, top_k=2)
    assert [i["id"] for i in result[0]] == ["b", "c"]   # 상위 2개만


def test_후보없는_질의는_빈리스트로_보존():
    result = _scatter_reranked(3, [{"id": "a"}], [1], [0.7], top_k=None)
    assert result[0] == []
    assert [i["id"] for i in result[1]] == ["a"]
    assert result[2] == []


def test_원본_item_불변():
    original = {"id": "a", "text": "t"}
    result = _scatter_reranked(1, [original], [0], [0.5], top_k=None)
    assert "rerank_score" not in original          # 얕은 복사 → 원본 오염 없음
    assert result[0][0]["rerank_score"] == 0.5
