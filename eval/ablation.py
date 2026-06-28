"""
[담당: 팀원 D] 리트리벌 변형군 비교 — RAG 정당성 증명 (기획서 8.5, 필수)

규격(통과해야 할 테스트): tests/eval/test_ablation.py
BM25 / dense / hybrid / hybrid+reranker 를 같은 골든셋으로 비교합니다.
순수 집계 run_ablation 은 eval.run_eval.evaluate 를 변형별로 호출해 재사용합니다.
"""
from typing import Dict, List


def run_ablation(cases_by_variant: Dict[str, List[Dict]], k: int = 5) -> Dict[str, Dict]:
    """
    변형별 검색 결과 케이스를 받아 변형별 지표 표를 만듭니다.
    입력: {"bm25": [cases...], "dense": [...], "hybrid": [...], "hybrid_rerank": [...]}
    반환: {variant: {"recall@k": float, "mrr": float, "n": int}}
    """
    raise NotImplementedError("담당: 팀원 D — tests/eval/test_ablation.py")
