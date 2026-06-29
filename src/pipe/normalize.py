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
from pathlib import Path
from typing import List

from contracts.enums import ContractType, Category
from contracts.models import Clause, StandardClause
from adapter import splitter, embedder

# "### 제12조(제목)" / "제12조 (제목)" 등에서 조번호·제목 추출 (도메인 규칙)
HEADER_RE = re.compile(r"^#*\s*(제\d+조)\s*[\(\（]?\s*([^\)\）\n]*)")

# ── 모듈 전역 싱글톤 ────────────────────────────────────────────────────────
# build_category_vectors() 호출 후 채워집니다.
_category_vectors: dict[Category, list[float]] | None = None


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


# ── [구버전 키워드 구현 — 교체 대상] ────────────────────────────────────────
# def label_category(num: str, title: str, text: str) -> Category:
#     search_text = f"{title} {text}".lower()
#     if "지식재산권" in search_text or "저작권" in search_text:
#         return Category.IP_OWNERSHIP
#     if "보수" in search_text or "대금" in search_text or "임금" in search_text:
#         return Category.PAYMENT          # ← "하자보수" 오탐 버그
#     if "비밀" in search_text:
#         return Category.CONFIDENTIALITY
#     if "손해배상" in search_text:
#         return Category.LIABILITY
#     if "2차적저작물" in search_text:
#         return Category.DERIVATIVE_WORK  # ← enum 삭제됨, AttributeError
#     if "과업" in search_text or "담당업무" in search_text:
#         return Category.SCOPE_SOW
#     if "해지" in search_text or "해제" in search_text:
#         return Category.TERMINATION
#     if "분쟁" in search_text or "관할법원" in search_text:
#         return Category.DISPUTE
#     if "근로시간" in search_text or "휴게시간" in search_text:
#         return Category.WORKING_HOURS
#     if "휴가" in search_text or "휴일" in search_text:
#         return Category.HOLIDAY_LEAVE
#     if "사회보험" in search_text:
#         return Category.SOCIAL_INSURANCE
#     return Category.SCOPE_SOW            # ← 미분류 조항 전부 오버킷 문제

# def normalize_file(md_path: str, contract_type: ContractType, version: str) -> List[StandardClause]:
#     """
#     하나의 변환 마크다운 파일을 03_normalized StandardClause 리스트로 정규화합니다.
#     clause_id 예: f"{contract_type.value.lower()}-art{N}" (제N조의 N).
#     source 예: f"{파일명} / {num}".
#     """
#     import os
#     with open(md_path, "r", encoding="utf-8") as f:
#         md_text = f.read()
        
#     file_name = os.path.basename(md_path)
#     clauses = split_markdown_clauses(md_text)
#     standard_clauses = []
    
#     for clause in clauses:
#         category = label_category(clause.num, clause.title, clause.text)
        
#         import re
#         match = re.search(r"제(\d+)조", clause.num)
#         n = match.group(1) if match else str(clause.idx)
        
#         clause_id = f"{contract_type.value.lower()}-art{n}"
#         source = f"{file_name} / {clause.num}"
        
#         sc = StandardClause(
#             clause_id=clause_id,
#             contract_type=contract_type,
#             category=category,
#             title=clause.title,
#             text=clause.text,
#             source=source,
#             version=version
#         )
#         standard_clauses.append(sc)
        
#     return standard_clauses

# ─────────────────────────────────────────────────────────────────────────────


def build_category_vectors() -> None:
    """
    embedder 로 각 Category.anchors 를 인코딩해 _category_vectors 를 초기화합니다.
    just build-db 단계에서 한 번만 호출합니다.

    구현 힌트:
        - global _category_vectors 선언 후 모듈 전역에 씁니다.
        - _embedder.embed_documents(cat.anchors) 로 앵커 임베딩 목록을 얻습니다.
        - numpy 로 평균(axis=0)을 내어 카테고리 대표 벡터를 만듭니다.
    """
    raise NotImplementedError


def label_category(num: str, title: str, text: str) -> Category:
    """
    embedder 로 쿼리를 인코딩하고 _category_vectors 와 코사인 유사도를 비교해 Category 를 반환합니다.
    embedder / _category_vectors 는 모듈 전역을 참조합니다 (monkeypatch 교체 가능).

    예외:
        ValueError — 최고 유사도가 임계값(0.45) 미달인 경우.
                     SCOPE_SOW 묵시적 fallback 금지 (AGENTS.md "조용한 실패 금지").

    구현 힌트:
        - 쿼리 문자열: f"{title} {text[:200]}"
        - _embedder.embed_documents([query])[0] 으로 쿼리 벡터를 얻습니다.
        - 임베딩이 L2 정규화되어 있다면 내적(dot product) = 코사인 유사도입니다.
    """
    raise NotImplementedError


def normalize_file(md_path: str, contract_type: ContractType, version: str) -> List[StandardClause]:
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
    raise NotImplementedError


if __name__ == "__main__":
    import os
    import json
    from pathlib import Path

    converted_dir = Path("data/02_converted")
    normalized_dir = Path("data/03_normalized")
    normalized_dir.mkdir(parents=True, exist_ok=True)

    for md_file in converted_dir.glob("*.md"):
        contract_type = ContractType.SW_FREELANCE
        if "예술" in md_file.name:
            contract_type = ContractType.ARTS_SERVICE
        elif "기간제" in md_file.name or "근로" in md_file.name:
            contract_type = ContractType.SW_EMPLOYMENT

        version = "2024"

        standard_clauses = normalize_file(str(md_file), contract_type, version)
        json_data = [sc.model_dump() for sc in standard_clauses]

        out_name = f"standard_clauses.{contract_type.value.lower()}.json"
        out_path = normalized_dir / out_name

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

    print("[OK] 정규화 완료!")
