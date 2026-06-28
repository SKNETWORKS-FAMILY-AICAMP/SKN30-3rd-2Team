"""core.traverse_related_risks 규격 테스트 — 의존성 그래프 DFS (고도화 A)."""
from core import traverse_related_risks


def test_연관조항을_따라_수집():
    adj = {"A": ["B", "C"], "B": ["D"], "C": []}
    assert traverse_related_risks(adj, "A") == ["B", "C", "D"]


def test_시작노드는_결과에서_제외():
    adj = {"A": ["B"], "B": ["A"]}  # 순환
    assert traverse_related_risks(adj, "A") == ["B"]


def test_고립노드는_빈결과():
    assert traverse_related_risks({"A": []}, "A") == []


def test_max_depth_제한():
    adj = {"A": ["B"], "B": ["C"], "C": ["D"]}
    # 깊이 1 탐색이면 직접 이웃까지만
    result = traverse_related_risks(adj, "A", max_depth=1)
    assert "B" in result
    assert "D" not in result
