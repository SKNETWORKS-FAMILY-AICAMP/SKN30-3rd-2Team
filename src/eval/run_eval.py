"""
[담당: 팀원 D] 골든셋으로 검색/이탈 탐지 평가 (기획서 8)

규격(통과해야 할 테스트): tests/eval/test_run_eval.py
순수 집계 함수 evaluate 는 eval.metrics 를 재사용합니다(중복 구현 금지).

Driver(트랙 A, 통합/수동 실행 — 단위테스트 밖): 골든셋(src/eval/golden/*.json)의 user_clause 를
실제 어댑터(vector·reranker)와 review_contract 전체 파이프에 흘려 cases 를 만들고,
run_eval.evaluate / eval.ablation.run_ablation / eval.metrics.precision_recall 로 집계합니다.
규격: docs/tasks/D_eval.md §Driver.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List

# adapter/contracts/pipe(src/ 하위) 를 import 하기 위해 모듈 경로에 추가 (실행 위치 무관)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval import metrics


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


# ─────────────────────────────────────────────────────────────────────────
# Driver (트랙 A) — 아래부터는 외부 인덱스(Chroma)·모델에 의존하는 통합 코드입니다.
# `just build-db` 로 인덱스가 준비된 뒤에만 동작하며, 단위테스트 대상이 아닙니다.
# ─────────────────────────────────────────────────────────────────────────

STANDARD_COLLECTION = "standard_clauses"
SEARCH_VARIANTS = ("bm25", "dense", "hybrid", "hybrid_rerank")


class NullGrounder:
    """평가 전용 no-op Grounder. review_contract 는 grounder 를 필수로 요구하지만,
    법령 근거 텍스트 자체는 결정론적 검색/분류 평가(deviation·toxic P/R) 대상이 아니므로
    외부 korean-law-mcp 호출을 생략해 평가 속도를 지키고 네트워크 의존을 없앤다.
    """

    def get_grounding(self, _category: Any) -> list:
        return []

    def query_law(self, _clause_text: str) -> list:
        return []


def build_cases(golden: List[Dict], search_type: str, k: int, contract_type: str) -> List[Dict]:
    """골든셋 조항을 지정한 검색 변형으로 검색해 (retrieved_ids, gold_id) cases 를 만듭니다.

    EXTRA(gold_clause_id=null) 케이스는 검색 정답이 없으므로 제외합니다.
    질의별 개별 search 대신 search_many/rerank_many 배치를 써서 임베딩 왕복을 N회→1회로
    줄입니다(07-01 결정 로그 §7 — search_many 도입 취지와 동일한 이유).
    hybrid_rerank 는 hybrid 로 넉넉히(k*4) 뽑은 뒤 rerank_many 로 재정렬합니다
    (07-01 §1 불변식: 매칭엔 rerank_score 만 사용).
    """
    from adapter import vector, reranker  # 지연 임포트: 모델 로드는 driver 실행 시에만

    scored = [g for g in golden if g.get("gold_clause_id") is not None]
    if not scored:
        return []

    queries = [g["user_clause"] for g in scored]
    type_filter = {"contract_type": contract_type}

    if search_type == "hybrid_rerank":
        pools = vector.search_many(STANDARD_COLLECTION, queries, "hybrid", type_filter, k * 4)
        hits_per_query = reranker.rerank_many(queries, pools, text_key="text", top_k=k)
    else:
        hits_per_query = vector.search_many(STANDARD_COLLECTION, queries, search_type, type_filter, k)

    return [
        {"retrieved_ids": [h["id"] for h in hits], "gold_id": g["gold_clause_id"]}
        for g, hits in zip(scored, hits_per_query)
    ]


def build_cases_by_variant(golden: List[Dict], k: int, contract_type: str) -> Dict[str, List[Dict]]:
    """4변형(bm25/dense/hybrid/hybrid_rerank) 전체에 대해 build_cases 를 호출합니다."""
    return {
        variant: build_cases(golden, variant, k, contract_type)
        for variant in SEARCH_VARIANTS
    }


def _load_standards(contract_type: str) -> List[Any]:
    """server.py `_load_standards(ct)` 와 동일한 패턴으로 계약 유형별 표준조항 전체를 로드합니다."""
    from adapter import db
    from contracts.models import StandardClause

    rows = db.fetch_all(
        "SELECT * FROM standard_clauses WHERE contract_type = ?",
        contract_type,
    )
    return [StandardClause(**row) for row in rows]


def review_golden_clauses(golden: List[Dict], contract_type: str) -> Dict[str, Any]:
    """골든 케이스 전체를 review_contract 로 **한 번에** 배치 검토해 case_id → DeviationResult 를 모읍니다.

    조항별로 review_contract 를 개별 호출하면 배치 크기가 항상 1이 되어 내부의
    search_many/rerank 배치화 이점이 사라집니다(07-01 §7). 그래서 계약 유형별로 전체
    골든 조항을 한 번에 review_contract 에 태우고, 반환된 결과에서 user_clause 텍스트가
    일치하는 항목만 추립니다. review_contract 는 매칭 안 된 나머지 표준조항을 MISSING
    (user_clause="") 으로 함께 반환하므로 자연히 제외됩니다.
    """
    from adapter import vector, reranker
    from contracts.enums import ContractType
    from contracts.models import Clause
    from pipe.review_pipe import review_contract

    ct = ContractType(contract_type)
    standards = _load_standards(contract_type)
    grounder = NullGrounder()

    clauses = [
        Clause(idx=i + 1, num="", title="", text=g["user_clause"])
        for i, g in enumerate(golden)
    ]
    review_results = review_contract(
        clauses, ct,
        retriever=vector,
        reranker=reranker,
        grounder=grounder,
        all_standard_clauses=standards,
    )

    by_text: Dict[str, Any] = {}
    for r in review_results:
        if r.user_clause:  # MISSING 결과(user_clause="")는 골든 케이스가 아니므로 제외
            by_text.setdefault(r.user_clause, r)

    return {
        g["case_id"]: by_text[g["user_clause"]]
        for g in golden
        if g["user_clause"] in by_text
    }


def deviation_precision_recall(golden: List[Dict], review_results: Dict[str, Any]) -> Dict[str, float]:
    """이탈 탐지 이진 Precision/Recall: 예측 = deviation != NONE, 정답 = gold_deviation != NONE."""
    from contracts.enums import Deviation

    predicted = {cid for cid, r in review_results.items() if r.deviation != Deviation.NONE}
    gold = {g["case_id"] for g in golden if g["gold_deviation"] != "NONE"}
    return metrics.precision_recall(predicted, gold)


def toxic_precision_recall(golden: List[Dict], review_results: Dict[str, Any]) -> Dict[str, float]:
    """독소 탐지 Precision/Recall: 예측 = toxic_patterns 비어있지 않음, 정답 = gold_toxic 존재."""
    predicted = {cid for cid, r in review_results.items() if r.toxic_patterns}
    gold = {g["case_id"] for g in golden if g.get("gold_toxic")}
    return metrics.precision_recall(predicted, gold)


def _load_golden(golden_dir: str = "src/eval/golden") -> List[Dict]:
    import glob
    import json

    golden: List[Dict] = []
    for path in sorted(glob.glob(f"{golden_dir}/*.json")):
        with open(path, encoding="utf-8") as f:
            golden.extend(json.load(f))
    return golden


def main(k: int = 5) -> None:
    from eval.ablation import run_ablation

    golden = _load_golden()
    print(f"=== 골든셋 로드: {len(golden)}건 ===\n")

    by_type: Dict[str, List[Dict]] = {}
    for g in golden:
        by_type.setdefault(g["contract_type"], []).append(g)

    print(f"── A-1. 검색 ablation (Recall@{k} · MRR) ──")
    combined: Dict[str, List[Dict]] = {v: [] for v in SEARCH_VARIANTS}
    for contract_type, cases in by_type.items():
        cbv = build_cases_by_variant(cases, k, contract_type)
        for variant, c in cbv.items():
            combined[variant].extend(c)

    table = run_ablation(combined, k=k)
    for variant in SEARCH_VARIANTS:
        report = table[variant]
        print(f"  {variant:15s} recall@{k}={report['recall@k']:.3f}  mrr={report['mrr']:.3f}  n={report['n']}")

    print("\n── A-2/A-3. 이탈·독소 분류 Precision/Recall (계약 유형별) ──")
    for contract_type, cases in by_type.items():
        review_results = review_golden_clauses(cases, contract_type)
        dev_pr = deviation_precision_recall(cases, review_results)
        tox_pr = toxic_precision_recall(cases, review_results)
        print(f"  [{contract_type}] n={len(cases)} (검토됨={len(review_results)})")
        print(f"    이탈 P/R : precision={dev_pr['precision']:.3f} recall={dev_pr['recall']:.3f}")
        print(f"    독소 P/R : precision={tox_pr['precision']:.3f} recall={tox_pr['recall']:.3f}")


if __name__ == "__main__":
    main()
