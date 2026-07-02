import os
import re
from typing import List

from contracts.ports import Parser
from contracts.models import Clause
from adapter import kordoc


class KordocParser(Parser):
    """
    kordoc CLI 어댑터로 문서를 마크다운으로 변환한 뒤, "제N조" 라인 경계로 조항을
    분해하는 Parser 포트 구현체입니다.

    ⚠️ 조항 경계는 마크다운 헤더(#) 유무에 의존하지 않습니다. 실제 계약서(DOCX/PDF)는
    kordoc 변환 시 "제N조"가 #-헤더가 아니라 **평문 문단**으로 나오는 경우가 많고, 헤더
    기반(splitter의 # 섹션)으로 끊으면 문서 전체가 한 청크가 되어 **조항 0건으로 축퇴**합니다.
    따라서 줄 시작의 "제\\d+조"(선택적 # 허용) 자체를 경계로 삼습니다.
    """

    # "### 제12조(제목)" · "제 2 조 (용어의 정의)" · "제1조 (목적) 본문…" 를 모두 매칭.
    # ^ 라인 시작에 고정 — 본문 중간의 "…전 제3조의 규정…" 같은 언급으로 인한 오분할 방지.
    HEADER_RE = re.compile(r"^\s*#*\s*제\s*(\d+)\s*조\s*[\(\（]?\s*([^\)\）\n]*)")

    def parse(self, file_path: str) -> List[Clause]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"계약서 파일을 찾을 수 없습니다: {file_path}")

        # 1. kordoc CLI 어댑터 호출하여 원본 파일을 마크다운 포맷 텍스트로 일괄 추출
        try:
            markdown_text = kordoc.parse_to_text(file_path)
        except Exception as e:
            raise RuntimeError(f"kordoc 문서 변환 오류: {e}") from e

        # 2. "제N조" 라인 경계로 조항 분해 (헤더 유무 무관)
        return self._segment_by_article(markdown_text)

    def _segment_by_article(self, markdown_text: str) -> List[Clause]:
        """마크다운 본문을 "제N조" 라인 경계로 분해한다.

        각 "제N조" 라인에서 다음 "제N조" 라인 직전까지가 한 조항의 본문(헤더 라인 포함)이다.
        첫 조항 앞의 전문(제목·계약 개요 등)은 조항이 아니므로 버린다.
        """
        segments: List[tuple[str, str, List[str]]] = []  # (num, title, [본문 라인들])
        for line in markdown_text.split("\n"):
            match = self.HEADER_RE.match(line)
            if match:
                num = f"제{match.group(1)}조"  # '제 1 조' 등 공백 변형을 정규화
                title = match.group(2).strip().strip("()").strip()
                segments.append((num, title, [line]))
            elif segments:  # 첫 "제N조" 이전의 전문은 무시, 이후엔 현재 조항 본문에 누적
                segments[-1][2].append(line)

        return [
            Clause(idx=idx, num=num, title=title, text="\n".join(body).strip())
            for idx, (num, title, body) in enumerate(segments, start=1)
        ]
