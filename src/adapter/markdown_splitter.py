"""
[공유 인프라] 마크다운 → 청크 분해 어댑터 (도메인 무관, 순수 split)

llama_index 의 MarkdownNodeParser 를 감싸 마크다운 헤더(#) 단위로 텍스트 청크를
나눠 반환합니다. "제N조" 같은 계약 도메인 해석은 여기서 하지 않습니다 → 그건 pipe.normalize.

재사용처: pipe.normalize(표준 코퍼스), 사용자 업로드 파싱(parse_contract).
"""
from typing import List

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser


class MarkdownSplitter:
    """MarkdownNodeParser 기반 순수 청크 분해기. (상태 없음 — 싱글톤 공유)"""

    def __init__(self):
        self._parser = MarkdownNodeParser()

    def split(self, md_text: str) -> List[str]:
        """
        마크다운 본문을 헤더(#) 섹션 단위 텍스트 청크 리스트로 분해합니다.
        각 청크는 자신의 헤더 라인을 포함합니다. 빈 청크는 제외합니다.
        """
        nodes = self._parser.get_nodes_from_documents([Document(text=md_text)])
        return [node.text.strip() for node in nodes if node.text.strip()]


# =================================================================
# 팀원 공용 마크다운 분해기 (Single Instance)
# 사용법: from adapter import splitter
#   chunks = splitter.split(md_text)   # -> List[str] (헤더 포함 청크)
# =================================================================
splitter = MarkdownSplitter()
