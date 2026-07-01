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
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# adapter/contracts/pipe(src/ 하위) 를 import 하기 위해 모듈 경로에 추가 (실행 위치 무관)
sys.path.append(str(Path(__file__).resolve().parent.parent))

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
    logger.info(f"[evaluate] 지표 집계 시작: n={n}건 (k={k})")

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


class _MemoizingEmbedder:
    """[eval 드라이버 전용] 임베더를 감싸 텍스트별로 임베딩을 캐시하는 국소 래퍼.

    골든셋은 고정·유계인데 A-1(dense·hybrid·hybrid_rerank)과 A-2(std·sub·toxic 컬렉션)가
    동일 조항을 반복 임베딩한다(프로덕션 기준 조항당 encode 6회). 드라이버가 도는 동안에만
    텍스트→벡터를 재사용해 이 중복을 없앤다. 프로덕션 싱글톤에 전역 캐시를 심으면 무한 증가·
    스레드 경쟁을 떠안으므로, 여기서는 단일 스레드 드라이버 실행 범위로 캐시를 국소화한다.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._cache: Dict[str, List[float]] = {}

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 캐시에 없는 텍스트만 중복 제거해 한 번에 배치 임베딩한 뒤, 요청 순서대로 복원한다.
        missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
        if missing:
            for text, vector in zip(missing, self._inner.embed_documents(missing)):
                self._cache[text] = vector
        return [self._cache[t] for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

    def __getattr__(self, name: str) -> Any:
        # embed 외 메서드(compute_similarity 등)는 원본 임베더에 그대로 위임한다.
        return getattr(self._inner, name)


def _install_eval_embedding_cache() -> None:
    """공유 VectorManager 싱글톤의 임베더를 드라이버 실행 동안 캐싱 래퍼로 교체한다.

    A-1·A-2 가 모두 `from adapter import vector` 로 같은 싱글톤을 쓰므로, 여기 한 곳만
    감싸면 전체 실행이 하나의 캐시를 공유해 골든 조항을 딱 한 번만 임베딩한다.
    이미 래핑돼 있으면(중복 호출) 그대로 둔다.
    """
    from adapter import vector

    if not isinstance(vector._embedder, _MemoizingEmbedder):
        vector._embedder = _MemoizingEmbedder(vector._embedder)


class NullGrounder:
    """평가 전용 no-op Grounder. review_contract 는 grounder 를 필수로 요구하지만,
    법령 근거 텍스트 자체는 결정론적 검색/분류 평가(deviation·toxic P/R) 대상이 아니므로
    외부 korean-law-mcp 호출을 생략해 평가 속도를 지키고 네트워크 의존을 없앤다.
    """

    def get_grounding(self, _category: Any) -> list:
        return []

    def query_law(self, _clause_text: str) -> list:
        return []


def build_cases_by_variant(golden: List[Dict], k: int, contract_type: str) -> Dict[str, List[Dict]]:
    """4변형(bm25/dense/hybrid/hybrid_rerank)의 (retrieved_ids, gold_id) cases 를 한 번에 만듭니다.

    EXTRA(gold_clause_id=null) 케이스는 검색 정답이 없으므로 제외합니다.
    질의별 개별 search 대신 search_many/rerank_many 배치를 써서 임베딩 왕복을 N회→1회로
    줄입니다(07-01 결정 로그 §7 — search_many 도입 취지와 동일한 이유).
    또한 hybrid 와 hybrid_rerank 는 동일한 hybrid 풀을 공유합니다 — k*4 로 넉넉히 **한 번만**
    검색해 hybrid 는 상위 k 슬라이스로, hybrid_rerank 는 rerank_many 재정렬로 얻습니다
    (중복 hybrid 검색 제거; 07-01 §1 불변식: 매칭엔 rerank_score 만 사용).
    """
    from adapter import vector, reranker  # 지연 임포트: 모델 로드는 driver 실행 시에만

    scored = [g for g in golden if g.get("gold_clause_id") is not None]
    if not scored:
        return {variant: [] for variant in SEARCH_VARIANTS}

    logger.info(f"[build_cases_by_variant] 검색 케이스 생성 중 (k={k}, contract_type={contract_type}, 대상 조항={len(scored)}건)...")
    queries = [g["user_clause"] for g in scored]
    gold_ids = [g["gold_clause_id"] for g in scored]
    type_filter = {"contract_type": contract_type}

    def _to_cases(hits_per_query: List[List[Dict]]) -> List[Dict]:
        return [
            {"retrieved_ids": [h["id"] for h in hits], "gold_id": gid}
            for gid, hits in zip(gold_ids, hits_per_query)
        ]

    bm25 = vector.search_many(STANDARD_COLLECTION, queries, "bm25", type_filter, k)
    dense = vector.search_many(STANDARD_COLLECTION, queries, "dense", type_filter, k)

    # hybrid 풀을 k*4 로 한 번만 검색 → hybrid(상위 k)·hybrid_rerank(재정렬)가 공유
    pool = vector.search_many(STANDARD_COLLECTION, queries, "hybrid", type_filter, k * 4)
    hybrid = [hits[:k] for hits in pool]
    reranked = reranker.rerank_many(queries, pool, text_key="text", top_k=k)

    return {
        "bm25": _to_cases(bm25),
        "dense": _to_cases(dense),
        "hybrid": _to_cases(hybrid),
        "hybrid_rerank": _to_cases(reranked),
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
    logger.info(f"[review_golden_clauses] 골든셋 조항 배치 검토 시작: contract_type={contract_type}, 조항={len(clauses)}개...")
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


def deviation_scores(golden: List[Dict], review_results: Dict[str, Any]) -> Dict[str, float]:
    """이탈 탐지 이진 지표(참음성 포함): 예측 = deviation != NONE, 정답 = gold_deviation != NONE.

    채점 대상(universe)은 실제 검토된 case_id 로 한정한다. specificity 가 낮으면
    정상 조항(gold_deviation="NONE")까지 이탈로 찍고 있다는 뜻 — recall 1.0 이 축퇴인지 판별한다.
    """
    from contracts.enums import Deviation

    universe = set(review_results.keys())
    predicted = {cid for cid, r in review_results.items() if r.deviation != Deviation.NONE}
    gold = {g["case_id"] for g in golden if g["gold_deviation"] != "NONE"}
    return metrics.binary_scores(predicted, gold, universe)


def toxic_scores(golden: List[Dict], review_results: Dict[str, Any]) -> Dict[str, float]:
    """독소 탐지 이진 지표(참음성 포함): 예측 = toxic_patterns 비어있지 않음, 정답 = gold_toxic 존재."""
    universe = set(review_results.keys())
    predicted = {cid for cid, r in review_results.items() if r.toxic_patterns}
    gold = {g["case_id"] for g in golden if g.get("gold_toxic")}
    return metrics.binary_scores(predicted, gold, universe)


GOLDEN_DIR = "src/eval/golden"


def _load_golden(version: str, golden_dir: str = GOLDEN_DIR) -> List[Dict]:
    """지정 버전의 골든셋(`{version}_*.json`)만 로드한다.

    같은 폴더에 v1·v2 가 공존해도 버전이 섞이지 않도록 파일명 접두사로 스코프한다.
    """
    import glob
    import json

    golden: List[Dict] = []
    for path in sorted(glob.glob(f"{golden_dir}/{version}_*.json")):
        with open(path, encoding="utf-8") as f:
            golden.extend(json.load(f))
    return golden


def _detect_latest_version(golden_dir: str = GOLDEN_DIR) -> str:
    """golden_dir 의 `v<N>_*.json` 을 스캔해 가장 높은 v<N> 을 반환한다 (없으면 'v1')."""
    import glob
    import os
    import re

    versions = set()
    for path in glob.glob(f"{golden_dir}/v*_*.json"):
        m = re.match(r"v(\d+)_", os.path.basename(path))
        if m:
            versions.add(int(m.group(1)))
    return f"v{max(versions)}" if versions else "v1"


def _write_result_md(
    version: str,
    total_n: int,
    overall_ablation: Dict[str, Dict],
    by_type: Dict[str, Dict[str, Any]],
    k: int,
    golden_dir: str = GOLDEN_DIR,
) -> str:
    """버전 전체 평가 결과를 **단일** `{version}_result.md` 로 저장하고 경로를 반환한다.

    협업 루프의 산출물 — 팀원이 골든셋 버전 간 지표를 diff 로 비교할 수 있게 결정론적 포맷으로 쓴다.
    A-1(검색)은 유형 합산 한 표, A-2/A-3(분류)는 계약 유형별 한 표로 담는다.
    by_type: {contract_type: {"n","reviewed","dev","tox"}}
    """
    from datetime import datetime

    from config import app_env

    path = str(Path(golden_dir) / f"{version}_result.md")

    lines = [
        f"# {version} — 평가 결과",
        "",
        f"> 자동 생성: `src/eval/run_eval.py` · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"· `APP_ENV={app_env}` · 골든 `{version}_*.json` (전체 n={total_n}, 유형 {len(by_type)}종)",
        "> 지표는 결정론적이며 LLM-judge 를 쓰지 않는다 (AGENTS.md #5).",
        "",
        f"## A-1. 검색 ablation — 전체 합산 (Recall@{k} · MRR)",
        "",
        f"| variant | recall@{k} | MRR | n |",
        "| --- | --- | --- | --- |",
    ]
    for variant in SEARCH_VARIANTS:
        r = overall_ablation[variant]
        lines.append(f"| {variant} | {r['recall@k']:.3f} | {r['mrr']:.3f} | {r['n']} |")

    lines += [
        "",
        "## A-2/A-3. 이탈·독소 분류 — 계약 유형별 (참음성 포함)",
        "",
        "| 유형 | n(검토됨) | 항목 | P | R | 특이도 | 정확도 | F1 | TP | FP | FN | TN |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for ct, m in by_type.items():
        head = f"{ct} | {m['n']}({m['reviewed']})"
        for label, s in (("이탈", m["dev"]), ("독소", m["tox"])):
            lines.append(
                f"| {head} | {label} | {s['precision']:.3f} | {s['recall']:.3f} | {s['specificity']:.3f} | "
                f"{s['accuracy']:.3f} | {s['f1']:.3f} | "
                f"{s['tp']:.0f} | {s['fp']:.0f} | {s['fn']:.0f} | {s['tn']:.0f} |"
            )
            head = " | "  # 같은 유형의 둘째 행은 유형·n 칸 비움
    lines += [
        "",
        "> 해석 주의: `특이도=0`(TN=0)은 정상·무해 케이스를 전부 양성으로 찍는 축퇴를 뜻한다. "
        f"근본 원인·강약점·다음 버전 반영점은 `{version}_review.md` 참조.",
        "",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def _run_track_a(k: int = 5, version: str | None = None) -> None:
    """트랙 A (합성 조항 단위): 검색 ablation + 이탈·독소 분류 → `{version}_result.md`."""
    from eval.ablation import run_ablation

    version = version or _detect_latest_version()
    golden = _load_golden(version)
    logger.info(f"=== [{version}] 골든셋 로드: {len(golden)}건 ===")

    by_type: Dict[str, List[Dict]] = {}
    for g in golden:
        by_type.setdefault(g["contract_type"], []).append(g)

    combined: Dict[str, List[Dict]] = {v: [] for v in SEARCH_VARIANTS}
    metrics_by_type: Dict[str, Dict[str, Any]] = {}
    for contract_type, cases in by_type.items():
        cbv = build_cases_by_variant(cases, k, contract_type)
        for variant, c in cbv.items():
            combined[variant].extend(c)

        review_results = review_golden_clauses(cases, contract_type)
        dev = deviation_scores(cases, review_results)
        tox = toxic_scores(cases, review_results)
        metrics_by_type[contract_type] = {
            "n": len(cases), "reviewed": len(review_results), "dev": dev, "tox": tox,
        }

        logger.info(f"── [{contract_type}] n={len(cases)} (검토됨={len(review_results)}) ──")
        logger.info(
            f"    이탈 : P={dev['precision']:.3f} R={dev['recall']:.3f} "
            f"특이도={dev['specificity']:.3f} 정확도={dev['accuracy']:.3f} F1={dev['f1']:.3f} "
            f"(TP={dev['tp']:.0f} FP={dev['fp']:.0f} FN={dev['fn']:.0f} TN={dev['tn']:.0f})"
        )
        logger.info(
            f"    독소 : P={tox['precision']:.3f} R={tox['recall']:.3f} "
            f"특이도={tox['specificity']:.3f} 정확도={tox['accuracy']:.3f} F1={tox['f1']:.3f} "
            f"(TP={tox['tp']:.0f} FP={tox['fp']:.0f} FN={tox['fn']:.0f} TN={tox['tn']:.0f})"
        )

    # 전체 합산 검색 ablation (유형 무관 대표 수치)
    overall = run_ablation(combined, k=k)
    logger.info(f"── [{version}] 전체 합산 A-1 (Recall@{k} · MRR) ──")
    for variant in SEARCH_VARIANTS:
        r = overall[variant]
        logger.info(f"    {variant:15s} recall@{k}={r['recall@k']:.3f}  mrr={r['mrr']:.3f}  n={r['n']}")

    out = _write_result_md(version, len(golden), overall, metrics_by_type, k)
    logger.info(f"=== 결과 저장: {out} ===")


# ─────────────────────────────────────────────────────────────────────────
# Track B (실계약 문서 단위) — MISSING Recall + 강건성. 상세 규격: docs/tasks/D_eval.md §트랙 B
# 합성 조항(트랙 A)과 달리 문서 1건을 KordocParser 로 실제 파싱해 server.py 와 동일 경로로 검토한다.
# ─────────────────────────────────────────────────────────────────────────

GOLDEN_B_DIR = "src/eval/golden_b"


def _load_labels_b(version: str, golden_b_dir: str = GOLDEN_B_DIR) -> List[Dict]:
    """`golden_b/labels/{version}_*.json` 계약 단위 정답 라벨을 로드한다."""
    import glob
    import json

    labels: List[Dict] = []
    for path in sorted(glob.glob(f"{golden_b_dir}/labels/{version}_*.json")):
        with open(path, encoding="utf-8") as f:
            labels.append(json.load(f))
    return labels


def review_document_b(doc_path: str, contract_type: str, golden_b_dir: str = GOLDEN_B_DIR) -> List[Any]:
    """실계약 문서 1건을 server.py 와 **동일 경로**(KordocParser.parse → review_contract)로 검토한다.

    Track B 스코프상 '지름길 없이 실제 파싱까지' 검증하므로 원본(HWP/PDF)을 직접 파싱한다.
    법령 근거(grounder)는 MISSING·deviation 판정과 무관하므로 NullGrounder 로 대체(네트워크 생략).
    doc_path 는 라벨의 상대경로(golden_b 기준) 또는 절대경로.
    """
    from contracts.enums import ContractType
    from contracts.implement import KordocParser
    from pipe.review_pipe import review_contract
    from adapter import vector, reranker

    ct = ContractType(contract_type)
    resolved = doc_path if Path(doc_path).is_absolute() else str(Path(golden_b_dir) / doc_path)
    clauses = KordocParser().parse(resolved)
    if not clauses:
        return []
    standards = _load_standards(contract_type)
    return review_contract(
        clauses, ct,
        retriever=vector, reranker=reranker, grounder=NullGrounder(),
        all_standard_clauses=standards,
    )


def summarize_review_b(results: List[Any]) -> Dict[str, Any]:
    """검토 결과에서 강건성 스팟체크용 요약을 뽑는다: 조항수·deviation 분포·NO_MATCH·MISSING 후보."""
    from contracts.enums import Deviation

    clause_results = [r for r in results if r.user_clause]  # 실제 사용자 조항 판정 (MISSING 은 user_clause="")
    missing = [r for r in results if r.deviation == Deviation.MISSING]
    dist: Dict[str, int] = {}
    for r in clause_results:
        dist[r.deviation.value] = dist.get(r.deviation.value, 0) + 1
    return {
        "n_clauses": len(clause_results),
        "deviation_dist": dist,
        "no_match": dist.get(Deviation.NO_MATCH.value, 0),
        "missing_ids": [r.matched_standard.clause_id for r in missing if r.matched_standard],
    }


def _dump_document_b(label: Dict, results: List[Any], summ: Dict[str, Any]) -> None:
    """사람 확인용 덤프(MISSING 후보 컨펌 + 강건성 스팟체크)를 stdout 으로 출력한다.

    라벨링은 '처음부터 쓰는' 게 아니라 **시스템 제안을 컨펌**하는 방식이므로, 확인 시
    시스템이 제안 못 한 누락도 사람이 독립적으로 찾아 expected_missing 에 넣어야 한다(순환 편향 방어).
    """
    cid = label["contract_id"]
    print(f"\n{'=' * 84}\n[{cid}] {label['contract_type']} · {label['doc_path']}\n{'=' * 84}")
    print(f"  파싱 조항수={summ['n_clauses']}  deviation 분포={summ['deviation_dist']}  NO_MATCH={summ['no_match']}")
    print(f"  MISSING 후보({len(summ['missing_ids'])}건) — 확인 후 expected_missing 에 반영:")
    for mid in summ["missing_ids"]:
        print(f"    - {mid}")
    print(f"  현재 라벨 expected_missing = {label.get('expected_missing', [])}")
    print("  ── 조항별 판정(강건성 스팟체크) ──")
    for r in results:
        if not r.user_clause:  # MISSING 은 위에서 이미 나열
            continue
        std = r.matched_standard.clause_id if r.matched_standard else "-"
        print(f"    [{r.deviation.value:8}] conf={r.confidence:.2f} match={std:28} :: {r.user_clause[:48]}")


def _write_result_b_md(version: str, per_doc: List[Dict], overall: Dict, golden_b_dir: str = GOLDEN_B_DIR) -> str:
    """Track B 결과를 `{version}_b_result.md` 로 저장(정량 MISSING Recall 표 + 사람이 채우는 강건성 섹션)."""
    from datetime import datetime

    from config import app_env

    path = str(Path(golden_b_dir) / f"{version}_b_result.md")
    lines = [
        f"# {version} · Track B (실계약) — 평가 결과",
        "",
        f"> 정량부 자동 생성: `eval.run_eval.evaluate_missing_recall` · "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · `APP_ENV={app_env}` · 문서 {overall['n_docs']}건",
        "> ⚠️ 표본이 작아 수치는 **방향 참고용**(최적화 목표 아님). 라벨이 시스템 제안 컨펌 기반이면 "
        "recall 이 낙관 편향됨(협업 규칙 — `src/eval/README.md` 참조).",
        "",
        "## MISSING Recall (문서별)",
        "",
        "| contract_id | 유형 | 조항수 | NO_MATCH | MISSING 예측 | 정답 | P | R |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for d in per_doc:
        lines.append(
            f"| {d['contract_id']} | {d['contract_type']} | {d['n_clauses']} | {d['no_match']} | "
            f"{d['n_predicted']} | {d['n_expected']} | {d['precision']:.3f} | {d['recall']:.3f} |"
        )
    lines += [
        "",
        f"**전체(micro):** precision={overall['precision']:.3f} · recall={overall['recall']:.3f} "
        f"(TP={overall['tp']} / 예측={overall['pred']} / 정답={overall['gold']})",
        "",
        "## 강건성 스팟체크 (사람 작성 — 정성, 지표 없음)",
        "",
        "> `python -m eval.dump_review_b` 출력을 훑고 아래를 채운다.",
        "",
        "- 파싱 성공/실패 · 깨진 조항 여부 — ",
        "- deviation 분포 이상 여부(NO_MATCH 폭주 등) — ",
        "- **시스템이 제안하지 못한 누락**(사람이 독립적으로 확인 — 순환 편향 방어) — ",
        "- 기타 — ",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def evaluate_missing_recall(
    version: str | None = None, golden_b_dir: str = GOLDEN_B_DIR,
    write_md: bool = True, verbose_dump: bool = False,
) -> Dict[str, Any]:
    """Track B 정량 지표: 문서별 MISSING id 집합 vs 라벨 `expected_missing` → `precision_recall`.

    표본이 매우 작으므로(문서 2~3건) 수치는 '목표'가 아니라 '방향 참고'다. 또한 라벨이 시스템 제안
    컨펌 기반이면 recall 이 낙관 편향됨을 유의(협업 규칙 — README §Track B).
    verbose_dump=True 면 문서를 한 번만 검토하면서 사람 확인용 덤프(MISSING 후보·강건성)도 함께 출력한다.
    """
    version = version or _detect_latest_version(f"{golden_b_dir}/labels")
    labels = _load_labels_b(version, golden_b_dir)
    logger.info(f"=== [Track B · {version}] 라벨 로드: {len(labels)}건 ===")

    per_doc: List[Dict[str, Any]] = []
    tp = pred = gold = 0
    for lb in labels:
        results = review_document_b(lb["doc_path"], lb["contract_type"], golden_b_dir)
        summ = summarize_review_b(results)
        if verbose_dump:
            _dump_document_b(lb, results, summ)
        predicted = set(summ["missing_ids"])
        expected = set(lb.get("expected_missing", []))
        pr = metrics.precision_recall(predicted, expected)
        tp += len(predicted & expected)
        pred += len(predicted)
        gold += len(expected)
        per_doc.append({
            "contract_id": lb["contract_id"], "contract_type": lb["contract_type"],
            "n_clauses": summ["n_clauses"], "no_match": summ["no_match"],
            "n_predicted": len(predicted), "n_expected": len(expected),
            "precision": pr["precision"], "recall": pr["recall"],
        })
        logger.info(
            f"  [{lb['contract_id']}] 조항={summ['n_clauses']} NO_MATCH={summ['no_match']} "
            f"MISSING 예측={len(predicted)}/정답={len(expected)} P={pr['precision']:.3f} R={pr['recall']:.3f}"
        )

    overall = {
        "precision": tp / pred if pred else 0.0,
        "recall": tp / gold if gold else 0.0,
        "tp": tp, "pred": pred, "gold": gold, "n_docs": len(labels),
    }
    if not labels:
        logger.info(f"Track B 라벨이 없습니다. {golden_b_dir}/labels/{version}_*.json 을 먼저 만드세요.")
        return {"version": version, "per_doc": [], "overall": overall, "result_md": None}

    logger.info(
        f"── [Track B · {version}] MISSING 전체(micro) P={overall['precision']:.3f} R={overall['recall']:.3f} ──"
    )
    out = _write_result_b_md(version, per_doc, overall, golden_b_dir) if write_md else None
    if out:
        logger.info(f"=== 결과 저장: {out} ===")
    return {"version": version, "per_doc": per_doc, "overall": overall, "result_md": out}


def _run_track_b(version: str | None = None) -> None:
    """트랙 B (실계약 문서 단위): 사람 확인용 덤프 + MISSING Recall → `{version}_b_result.md`.

    문서를 한 번만 검토하며 (1) MISSING 후보·강건성 덤프 출력, (2) 정량 지표 계산·저장을 함께 한다.
    """
    version = version or _detect_latest_version(f"{GOLDEN_B_DIR}/labels")
    evaluate_missing_recall(version, write_md=True, verbose_dump=True)


def main(track: str = "a", version: str | None = None, k: int = 5) -> None:
    """평가 드라이버 진입점. track 인자로 트랙을 분기한다(기본 'a').

    - track='a': 합성 조항 단위(검색·이탈·독소). `{version}_result.md` 생성.
    - track='b': 실계약 문서 단위(MISSING Recall·강건성). `{version}_b_result.md` 생성.
    """
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
    _install_eval_embedding_cache()  # 임베딩 중복 제거 (드라이버 전용 국소 캐시 — 두 트랙 공통)

    if track == "b":
        _run_track_b(version)
    else:
        _run_track_a(k, version)


if __name__ == "__main__":
    # 사용법: python -m eval.run_eval [a|b] [version]
    #   python -m eval.run_eval            # 트랙 A, 최신 버전
    #   python -m eval.run_eval b          # 트랙 B, 최신 버전
    #   python -m eval.run_eval a v2       # 트랙 A, v2
    _track = sys.argv[1] if len(sys.argv) > 1 else "a"
    _version = sys.argv[2] if len(sys.argv) > 2 else None
    main(track=_track, version=_version)
