import os
import re
from typing import List

from contracts.ports import Parser
from contracts.models import Clause
from adapter import kordoc, splitter

class KordocParser(Parser):
    """
    kordoc CLI 어댑터와 마크다운 분해기(splitter)를 조합하여
    한글/PDF 계약서 문서를 구조화된 Clause 목록으로 분해하는 Parser 포트 구현체입니다.
    """

    def parse(self, file_path: str) -> List[Clause]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"계약서 파일을 찾을 수 없습니다: {file_path}")

        # 1. kordoc CLI 어댑터 호출하여 원본 파일을 마크다운 포맷 텍스트로 일괄 추출
        try:
            markdown_text = kordoc.parse_to_text(file_path)
        except Exception as e:
            raise RuntimeError(f"kordoc 문서 변환 오류: {e}") from e

        # 2. 마크다운 분해 어댑터(splitter)를 사용해 헤더(#) 단위 섹션 분할
        chunks = splitter.split(markdown_text)

        # 3. 조항 형태의 헤더를 지닌 본문 섹션만 식별하여 Clause 객체 목록 생성
        # 정규식 패턴 예: '### 제12조(제목)' 또는 '## 제 2 조 (용어의 정의)'
        HEADER_RE = re.compile(r"^\s*#*\s*(제\s*\d+\s*조)\s*[\(\（]?\s*([^\)\）\n]*)")

        clauses = []
        idx = 1
        for chunk in chunks:
            lines = chunk.strip().split("\n")
            if not lines:
                continue
            first_line = lines[0].strip()
            match = HEADER_RE.match(first_line)
            if match:
                num = match.group(1).replace(" ", "").strip()  # '제 1 조' -> '제1조'
                title = match.group(2).strip().strip("()").strip()

                # 본문(text)은 헤더 라인을 포함한 해당 분할 청크 본문 전체를 유지합니다.
                clauses.append(
                    Clause(
                        idx=idx,
                        num=num,
                        title=title,
                        text=chunk.strip()
                    )
                )
                idx += 1

        return clauses
