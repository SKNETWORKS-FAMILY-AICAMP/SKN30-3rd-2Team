import re
from typing import List

from contracts.ports import Grounder
from contracts.enums import Category
from contracts.models import GroundingLaw
from adapter import koreanLaw

# 계약 카테고리와 매칭되는 국가 법제처 표준 검색어 정의
CATEGORY_QUERIES = {
    Category.PAYMENT: "민법 제665조 보수의 지급시기",
    Category.IP_OWNERSHIP: "저작권법 제10조 및 지식재산권 귀속",
    Category.DERIVATIVE_WORK: "저작권법 제22조 2차적저작물작성권",
    Category.SCOPE_SOW: "민법 제664조 도급의 의의",
    Category.TERMINATION: "민법 제673조 완성전의 도급인의 해제권",
    Category.CONFIDENTIALITY: "부정경쟁방지 및 영업비밀보호에 관한 법률 제2조 영업비밀",
    Category.LIABILITY: "민법 제390조 채무불이행과 손해배상",
    Category.DISPUTE: "민사소송법 제29조 합의관할",
    Category.WORKING_HOURS: "근로기준법 제50조 근로시간",
    Category.HOLIDAY_LEAVE: "근로기준법 제60조 연차 유급휴가",
    Category.SOCIAL_INSURANCE: "고용보험법 및 국민건강보험법 사회보험",
}

class KoreanLawGrounder(Grounder):
    """
    korean-law MCP 클라이언트 어댑터를 사용하여, 특정 계약서 분류(Category) 또는
    본문 내용에 부합하는 근거 법조문을 수집하는 Grounder 포트 구현체입니다.
    """

    def _parse_raw_text_to_laws(self, query_str: str, raw_text: str) -> List[GroundingLaw]:
        """조회된 줄글 형태의 법령 정보 텍스트를 구조화된 GroundingLaw 리스트로 가공합니다."""
        # 1. 쿼리 키워드에서 기본 법령 이름 유추 (예: '저작권법 제10조' -> '저작권법')
        law_name_match = re.search(r"([가-힣]+법)", query_str)
        fallback_law_name = law_name_match.group(1) if law_name_match else "관련 법령"

        # 2. 본문에서 조항 단위 헤더 매칭 (예: '### 제5조(저작물)' 또는 '제17조 (비밀준수)')
        article_pattern = re.compile(r"(?:###?\s*)?(?:\[([^\]]+)\]\s*)?(제\s*\d+\s*조(?:\s*의\s*\d+)?)\s*([^\n]*)")
        matches = list(article_pattern.finditer(raw_text))

        if not matches:
            # 매칭되는 조항 번호 서식이 없는 경우 텍스트 전체를 하나의 근거 법률로 반환
            art_match = re.search(r"(제\s*\d+\s*조)", query_str)
            art_num = art_match.group(1) if art_match else "기본 조항"
            return [
                GroundingLaw(
                    법령명=fallback_law_name,
                    조번호=art_num,
                    본문=raw_text.strip(),
                    출처="국가법령정보센터"
                )
            ]

        grounding_laws = []
        for i, match in enumerate(matches):
            parsed_law_name = match.group(1) or fallback_law_name
            article_num = match.group(2).strip()
            title = match.group(3).strip().strip("()").strip()

            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)

            body = raw_text[start_pos:end_pos].strip()

            grounding_laws.append(
                GroundingLaw(
                    법령명=parsed_law_name,
                    조번호=article_num,
                    본문=f"({title})\n{body}" if title else body,
                    출처="국가법령정보센터"
                )
            )

        return grounding_laws

    def get_grounding(self, category: Category) -> List[GroundingLaw]:
        """주어진 조항 분류 카테고리에 대한 국가 표준 근거 법조문을 수집합니다."""
        query_str = CATEGORY_QUERIES.get(category, "민법 도급")
        try:
            # MCP 클라이언트를 호출해 원본 법령 정보 획득
            raw_text = koreanLaw.query(query_str)
        except Exception as e:
            print(f"[Warning] 법률 수집 실패 (카테고리: {category}): {e}")
            return []

        return self._parse_raw_text_to_laws(query_str, raw_text)

    def query_law(self, clause_text: str) -> List[GroundingLaw]:
        """사용자 조항 본문 텍스트에 부합하는 연관 근거 법령 정보를 동적 질의하여 수집합니다."""
        # 명령어 버퍼 문제를 피하기 위해 동적 검색어는 60자로 슬라이싱 처리
        query_str = clause_text.strip()[:60]
        try:
            raw_text = koreanLaw.query(query_str)
        except Exception as e:
            print(f"[Warning] 법률 수집 실패 (질의: {query_str}): {e}")
            return []

        return self._parse_raw_text_to_laws(query_str, raw_text)
