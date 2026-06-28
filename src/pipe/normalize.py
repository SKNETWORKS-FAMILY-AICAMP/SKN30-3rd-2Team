"""
[담당: 팀원 A] 마크다운 → 표준조항 정규화 (도메인 로직)

규격(통과해야 할 테스트): tests/pipe/test_normalize.py
참고: src/pipe/README.md, data/README.md, 기획서 3·5장

순수 마크다운 분해는 adapter.splitter 를 재사용합니다(중복 구현 금지).
이 모듈의 책임은 "제N조" 해석·category 라벨링 등 **계약 도메인 판단**입니다.
"""
import re
from typing import List

from contracts.enums import ContractType, Category
from contracts.models import Clause, StandardClause
from adapter import splitter

# "### 제12조(제목)" / "제12조 (제목)" 등에서 조번호·제목 추출 (도메인 규칙)
HEADER_RE = re.compile(r"^#*\s*(제\d+조)\s*[\(\（]?\s*([^\)\）\n]*)")


def split_markdown_clauses(md_text: str) -> List[Clause]:
    """
    adapter.splitter 로 청크를 나눈 뒤, "제N조" 헤더 청크만 골라 Clause 로 변환합니다.
    전문/개요 등 "제N조"가 아닌 청크는 제외합니다.
    """
    # TODO(팀원 A): splitter.split(md_text) 결과를 순회하며 HEADER_RE 로 num/title 추출,
    #   본문과 함께 Clause(idx, num, title, text) 생성. idx 는 1부터.
    raise NotImplementedError("담당: 팀원 A — tests/pipe/test_normalize.py 의 split 테스트")


def label_category(num: str, title: str, text: str) -> Category:
    """
    조항 제목·본문의 키워드로 Category 를 부여합니다. (도메인 규칙)
    예) "지식재산권"·"저작권" → IP_OWNERSHIP, "보수"·"대금" → PAYMENT,
        "비밀" → CONFIDENTIALITY, "손해배상" → LIABILITY ...
    """
    # TODO(팀원 A): 키워드 → Category 매핑 규칙 작성. 매칭 안 되면 가장 가까운 값 또는 규칙 정의.
    raise NotImplementedError("담당: 팀원 A — tests/pipe/test_normalize.py 의 label 테스트")


def normalize_file(md_path: str, contract_type: ContractType, version: str) -> List[StandardClause]:
    """
    하나의 변환 마크다운 파일을 03_normalized StandardClause 리스트로 정규화합니다.
    clause_id 예: f"{contract_type.value.lower()}-art{N}" (제N조의 N).
    source 예: f"{파일명} / {num}".
    """
    # TODO(팀원 A): split_markdown_clauses + label_category 조립 → StandardClause 생성.
    raise NotImplementedError("담당: 팀원 A — 03_normalized JSON 산출용")


if __name__ == "__main__":
    # TODO(팀원 A): data/02_converted/*.md 순회 → normalize_file → data/03_normalized/*.json 저장
    raise SystemExit("CLI 구현 예정 — pipe.normalize.normalize_file 사용 (담당: 팀원 A)")
