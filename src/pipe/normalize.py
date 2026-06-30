"""
[담당: 팀원 A] 마크다운 → 표준조항 정규화 (도메인 로직)

규격(통과해야 할 테스트): tests/pipe/test_normalize.py
참고: src/pipe/README.md, data/README.md, 기획서 3·5장, docs/tasks/A_normalize.md 리뷰 섹션

순수 마크다운 분해는 adapter.splitter 를 재사용합니다(중복 구현 금지).
이 모듈의 책임은 "제N조" 해석·category 라벨링 등 **계약 도메인 판단**입니다.
"""
import json
import os
import re
import sys
import numpy as np  
import logging
from pathlib import Path
from typing import List

# src/ 패키지 절대 경로 추가 (스크립트로 직접 실행하기 위함)
sys.path.append(str(Path(__file__).resolve().parent.parent))
from contracts.models import StandardSubChunk
from contracts.enums import ContractType, Category
from contracts.models import Clause, StandardClause
from adapter import splitter, embedder

# "### 제12조(제목)" / "제12조 (제목)" 등에서 조번호·제목 추출 (도메인 규칙)
HEADER_RE = re.compile(r"^#*\s*(제\d+조)\s*[\(\（]?\s*([^\)\）\n]*)")

# ── 모듈 전역 싱글톤 ────────────────────────────────────────────────────────
_embedder = embedder
# build_category_vectors() 호출 후 채워집니다.
# 각 Category 마다 "앵커별 벡터 행렬"(shape: 앵커수 × 차원)을 보관합니다.
# 평균(mean-pooling) 대신 max-pooling 으로 비교하기 위해 앵커를 합치지 않습니다.
_category_vectors: dict[Category, list[list[float]]] | None = None

# 카테고리 판정 임계값/마진 (max-pool 코사인 유사도 기준)
# 실측: 합성 테스트 문장은 0.6~1.0, 실제 법령 조항은 0.40~0.55 대에 분포.
# 어느 카테고리에도 안 맞는 조항("기본원칙" 등)은 절대점수가 아니라 1·2위가
# 거의 동점(마진≈0)이라는 점으로 구분된다. 표준 코퍼스는 절대 드롭하지 않으므로,
# 임계값 미만이면 Category.GENERAL 로 귀결시킨다(예외/None 금지).
_SCORE_THRESHOLD = 0.40  # 최고 점수가 이보다 낮으면 GENERAL 로 분류
_MARGIN_THRESHOLD = 0.02  # 1·2위 점수 차가 이보다 작으면 "근접"으로 보고 구체성 우선순위로 결정

# 단일 라벨 강제 시, 여러 카테고리가 마진 내로 근접하면 더 "구체적/사건 중심"인 쪽을 택한다.
# (예: "해지 시 기성 대금 정산" → PAYMENT 보다 TERMINATION). 인덱스가 작을수록 우선.
# 결정론적·재현 가능해야 하므로 명시적 순서로 고정한다(AGENTS.md).
_CATEGORY_PRECEDENCE: list[Category] = [
    # 특화·사건 중심 (우선)
    Category.TERMINATION,
    Category.IP_OWNERSHIP,
    Category.CONFIDENTIALITY,
    Category.WARRANTY,
    Category.DELIVERY_INSPECTION,
    Category.SUBCONTRACTING,
    Category.SOCIAL_INSURANCE,
    Category.DISPUTE,
    Category.WORKING_HOURS,
    Category.HOLIDAY_LEAVE,
    # 메커니즘·포괄
    Category.PAYMENT,
    Category.LIABILITY,
    Category.SCOPE_SOW,
    Category.CONTRACT_PERIOD,
    # 최후 (캐치올)
    Category.GENERAL,
]
_PRECEDENCE_RANK: dict[Category, int] = {c: i for i, c in enumerate(_CATEGORY_PRECEDENCE)}


def split_markdown_clauses(md_text: str) -> List[Clause]:
    """
    adapter.splitter 로 청크를 나눈 뒤, "제N조" 헤더 청크만 골라 Clause 로 변환합니다.
    전문/개요 등 "제N조"가 아닌 청크는 제외합니다.
    """
    chunks = splitter.split(md_text)
    clauses = []
    idx = 1
    for chunk in chunks:
        chunk_stripped = chunk.strip()
        match = HEADER_RE.match(chunk_stripped)
        if match:
            num = match.group(1).strip()
            title = match.group(2).strip()
            clauses.append(Clause(idx=idx, num=num, title=title, text=chunk_stripped))
            idx += 1
    return clauses

def build_category_vectors() -> None:
    """
    embedder 로 각 Category.anchors 를 인코딩해 _category_vectors 를 초기화합니다.
    just build-db 단계에서 한 번만 호출합니다.

    평균(mean-pooling)을 내지 않고 **앵커별 벡터를 그대로 보관**합니다.
    DELIVERY_INSPECTION(납품 + 검수)처럼 의미가 두 갈래인 카테고리는 평균을 내면
    어느 쪽에도 안 맞는 중심벡터가 되므로, label_category 에서 max-pooling 으로 비교합니다.
    """
    global _category_vectors
    if _category_vectors is not None:
        return

    _category_vectors = {}

    # 1. 임베딩할 카테고리와 앵커 텍스트를 모으기
    categories_to_embed = []
    all_anchors = []
    cat_lengths = []

    for cat in Category:
        if not hasattr(cat, 'anchors') or not cat.anchors:
            continue
        categories_to_embed.append(cat)
        all_anchors.extend(cat.anchors)
        cat_lengths.append(len(cat.anchors))

    if not all_anchors:
        return

    # 2. 단 한 번의 배치 호출로 전체 임베딩 구하기 (GPU 병렬 연산 극대화)
    #    embedder 는 normalize_embeddings=True 라 각 벡터의 L2 노름이 1.0 입니다.
    all_vectors = _embedder.embed_documents(all_anchors)

    # 3. 슬라이싱하여 각 카테고리별 "앵커 벡터 행렬" 보관 (평균 내지 않음)
    start_idx = 0
    for cat, length in zip(categories_to_embed, cat_lengths):
        end_idx = start_idx + length
        _category_vectors[cat] = all_vectors[start_idx:end_idx]
        start_idx = end_idx


def _maxpool_scores(q_vec: np.ndarray, categories: list[Category]) -> np.ndarray:
    """쿼리 벡터와 각 카테고리 앵커들 간 코사인 유사도의 최댓값(max-pool)을 반환합니다."""
    scores = np.empty(len(categories), dtype=np.float64)
    for i, cat in enumerate(categories):
        anchors = np.asarray(_category_vectors[cat])  # (앵커수, 차원)
        scores[i] = np.max(anchors @ q_vec)           # 가장 가까운 앵커 1개의 유사도
    return scores

def _parse_sub_chunks(rows: list[StandardClause]) -> list[StandardSubChunk]:
    sub_chunks = []
    
    # 2. 거대 조항 서브청킹 로직
    for r in rows:
        clause_id = r.clause_id
        text = r.text
        
        symbols = re.findall(r"[①-⑳]", text)
        nums = re.findall(r"^[0-9]+\.", text, flags=re.MULTILINE)
        
        # 500자 초과 OR 기호 3개 이상이면 쪼개기 (분할 조건)
        if len(text) > 300 or (len(symbols) + len(nums)) >= 3:
            parts = re.split(r"(^[①-⑳]|^[0-9]+\.)", text, flags=re.MULTILINE)
            
            current_chunk = parts[0].strip()
            idx = 0
            
            if current_chunk:
                sub_chunks.append(
                    StandardSubChunk(
                        sub_chunk_id=f"{clause_id}-sub{idx:02d}",
                        parent_clause_id=clause_id,
                        sub_chunk_index=idx,
                        text=current_chunk
                    )
                )
                idx += 1
                
            for i in range(1, len(parts), 2):
                symbol = parts[i]
                content = parts[i+1] if i+1 < len(parts) else ""
                chunk_text = (symbol + content).strip()
                if chunk_text:
                    sub_chunks.append(
                        StandardSubChunk(
                            sub_chunk_id=f"{clause_id}-sub{idx:02d}",
                            parent_clause_id=clause_id,
                            sub_chunk_index=idx,
                            text=chunk_text
                        )
                    )
                    idx += 1
        else:
            # 쪼개지 않고 조 전체를 1청크로 유지
            sub_chunks.append(
                StandardSubChunk(
                    sub_chunk_id=f"{clause_id}-sub00",
                    parent_clause_id=clause_id,
                    sub_chunk_index=0,
                    text=text
                )
            )
    return sub_chunks

def label_category(title: str, text: str) -> Category:
    """
    제목/본문을 임베딩하고 _category_vectors 와 코사인 유사도를 비교해 단일 Category 를 반환합니다.

    - max-pooling: 카테고리 점수 = 그 카테고리 앵커 중 가장 가까운 1개와의 유사도.
    - 제목 우선: 제목 단독 쿼리와 (제목+본문) 쿼리를 각각 비교한 뒤 카테고리별로 max 를 취해,
      본문 노이즈가 제목 신호를 끌어내리지 못하게 합니다.
    - 저점수(임계값 미만): 특정 카테고리 없음 → Category.GENERAL 로 분류 (드롭/예외 금지).
    - 근접(마진 내 복수 후보): 단일 라벨 강제 + 구체성 우선 규칙으로 더 구체적인 카테고리 선택.

    num 은 시그니처 호환을 위해 받지만 현재 판정에는 사용하지 않습니다.
    """
    if _category_vectors is None:
        raise RuntimeError("Category vectors are not initialized")

    title_query = title.strip()
    full_query = f"{title} {text[:200]}".strip()

    # 제목 단독 / 제목+본문 두 쿼리를 한 번에 임베딩
    q_title, q_full = (np.asarray(v) for v in _embedder.embed_documents([title_query, full_query]))

    # GENERAL 은 앵커가 비어 _category_vectors 에 없으므로 자연히 점수 경쟁에서 빠진다.
    categories = list(_category_vectors.keys())
    # 카테고리별로 두 쿼리 점수 중 더 높은 쪽 채택 (제목이 본문 노이즈에 묻히지 않도록)
    scores = np.maximum(_maxpool_scores(q_title, categories), _maxpool_scores(q_full, categories))

    best_score = float(scores.max())

    # 어느 카테고리와도 충분히 가깝지 않으면 일반 조항으로 귀결 (silent-drop 금지)
    if best_score < _SCORE_THRESHOLD:
        return Category.GENERAL

    # 최고점에서 마진 내로 근접한 후보들 중 가장 구체적인(우선순위 높은) 카테고리를 단일 선택
    near_idx = np.where(scores >= best_score - _MARGIN_THRESHOLD)[0]
    candidates = [categories[i] for i in near_idx]
    return min(candidates, key=lambda c: _PRECEDENCE_RANK[c])


def normalize_file(md_path: str, contract_type: ContractType, version: str) ->  tuple[List[StandardClause], List[StandardSubChunk]]:
    """
    마크다운 파일 하나를 StandardClause 리스트로 정규화합니다.

    반환:
        StandardClause 리스트 (clause_id, contract_type, category, title, text, source, version)

    규칙:
        - clause_id 형식: "{contract_type.value.lower()}-art{N}"  예) "sw_freelance-art6"
        - source 형식:    "{파일명} / {num}"                       예) "201231_SW종사자.md / 제6조"

    구현 힌트:
        split_markdown_clauses → label_category → StandardClause 조립
    """
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
        
    file_name = os.path.basename(md_path)
    clauses = split_markdown_clauses(md_text)
    standard_clauses = []
    seen_ids = set()
    
    for clause in clauses:
        # 표준 조항은 절대 드롭하지 않는다. 특정 카테고리가 없으면 GENERAL 로 분류된다.
        category = label_category(clause.title, clause.text)

        match = re.search(r"제(\d+)조", clause.num)
        n = match.group(1) if match else str(clause.idx)
        
        base_id = f"{contract_type.value.lower()}-{version}-art{n}"
        clause_id = base_id
        suffix = 2
        while clause_id in seen_ids:
            clause_id = f"{base_id}_{suffix}"
            suffix += 1
        seen_ids.add(clause_id)
        
        source = f"{file_name} / {clause.num}"
        
        sc = StandardClause(
            clause_id=clause_id,
            contract_type=contract_type,
            category=category,
            title=clause.title,
            text=clause.text,
            source=source,
            version=version
        )
        standard_clauses.append(sc)
        
    # 🌟 생성된 표준 조항들로부터 서브청크 추출 및 검증 반환
    valid_sub_chunks = _parse_sub_chunks(standard_clauses)
    
    return standard_clauses, valid_sub_chunks


if __name__ == "__main__":
    import config
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    FILENAME_CONTRACT = {
        "201231_SW종사자_기간제,단시간__표준근로계약서.md": ContractType.SW_EMPLOYMENT,
        "201231_SW종사자_표준도급계약서.md": ContractType.SW_FREELANCE,
        "221228_상용소프트웨어_공급개발구축업.md": ContractType.SI_SUBCONTRACT,
        "221228_상용소프트웨어_유지관리업종.md": ContractType.SM_SUBCONTRACT,
        "251221_상용소프트웨어공급개발구축업종(비밀유지계약서_통합_및_안전등_추가).md": ContractType.SI_SUBCONTRACT,
        "251221_상용소프트웨어유지관리업종(비밀유지계약서_통합_및_안전_추가).md": ContractType.SM_SUBCONTRACT
    }

    converted_dir = config.BASE_DIR / "data" / "02_converted"
    normalized_dir = config.BASE_DIR / "data" / "03_normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    # 1. 전역 카테고리 벡터 초기화 (필수)
    logging.info("[INFO] AI 임베딩 카테고리 벡터를 초기화합니다...")
    build_category_vectors()

    for md_file in converted_dir.glob("*.md"):
        # 명시적 실패(Fail-fast)
        if md_file.name not in FILENAME_CONTRACT:
            raise KeyError(f"정의되지 않은 계약서 파일입니다: {md_file.name}. FILENAME_CONTRACT 사전에 추가하세요.")
            
        contract_type = FILENAME_CONTRACT[md_file.name]
        version = f"20{md_file.name[:2]}"

        logging.info(f"[PROCESS] {md_file.name} -> {contract_type.value}")
        standard_clauses, sub_chunks = normalize_file(str(md_file), contract_type, version)
        
        # 1) standard_clauses JSON 저장
        json_data = [sc.model_dump() for sc in standard_clauses]
        out_name = f"standard_clauses.{contract_type.value.lower()}.{version}.json"
        out_path = normalized_dir / out_name

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # 2) standard_sub_chunks JSON 저장
        if sub_chunks:
            sub_chunk_data = [sc.model_dump() for sc in sub_chunks]
            sub_chunk_out_name = f"standard_sub_chunks.{contract_type.value.lower()}.{version}.json"
            sub_chunk_out_path = normalized_dir / sub_chunk_out_name
            with open(sub_chunk_out_path, "w", encoding="utf-8") as f:
                json.dump(sub_chunk_data, f, ensure_ascii=False, indent=2)

    logging.info("[OK] 전체 정규화 완료!")
