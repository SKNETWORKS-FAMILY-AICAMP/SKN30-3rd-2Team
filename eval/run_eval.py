"""
[담당: 팀원 D] 골든셋으로 검색/이탈 탐지 평가 (기획서 8)

규격(통과해야 할 테스트): tests/eval/test_run_eval.py
순수 집계 함수 evaluate 는 eval.metrics 를 재사용합니다(중복 구현 금지).
CLI 부분(골든셋 → review 파이프 → retrieved_ids 수집)은 통합/수동 실행입니다.
"""
from typing import List, Dict
from eval import metrics
from src.adapter import vector

def build_cases(golden: List[Dict], search_type: str, k: int, contract_type: str) -> List[Dict]:
    cases = []
    for g in golden:
        if g.get("gold_clause_id") is None:
            continue
        
        hits = vector.search(
            collection_name="standard_clauses",                         # TODO
            query=g["user_clause"],
            search_type=search_type,
            metadata_filter={"contract_type": contract_type},
            top_k=k
        )
        
        cases.append({
            "retrieved_ids": [h["id"] for h in hits], 
            "gold_id": g["gold_clause_id"]
        })
    return cases

def evaluate(cases: List[Dict], k: int = 5) -> Dict:
    """
    검색 결과 케이스들을 지표로 집계합니다.
    cases 각 항목: {"retrieved_ids": list[str], "gold_id": str}
    반환: {"recall@k": float, "mrr": float, "n": int}
    """
    if not cases:
        return {"recall@k": 0.0, "mrr": 0.0, "n": 0}

    n = len(cases)
    
    # 1. Recall@K 집계
    recalls = [
        metrics.recall_at_k(c["retrieved_ids"], c["gold_id"], k) 
        for c in cases
    ]
    avg_recall = sum(recalls) / n
    
    # 2. MRR 집계
    # metrics.mrr은 (retrieved_ids, gold_id) 튜플 리스트를 입력으로 받음
    rr_cases = [(c["retrieved_ids"], c["gold_id"]) for c in cases]
    avg_mrr = metrics.mrr(rr_cases)
    
    return {
        "recall@k": avg_recall,
        "mrr": avg_mrr,
        "n": n
    }
