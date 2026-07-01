"""
항·호 단위 조항 분할기 (순수 함수)

오프라인(normalize.py) 과 런타임(review_pipe.py 커버리지 체크) 이 동일 조건을 공유합니다.
외부 의존성 없음 — re 표준 라이브러리만 사용.
"""
import re

# 분할 대상 판정 임계값 — 오프라인·런타임 공유 (한 곳에서만 관리)
_LARGE_CLAUSE_CHAR_LIMIT = 300
_LARGE_CLAUSE_SYMBOL_LIMIT = 3

# 항·호 기호 패턴 (①~⑳, 줄 시작 숫자+점)
_SYMBOL_RE = re.compile(r"[①-⑳]")
_NUM_RE = re.compile(r"^[0-9]+\.", re.MULTILINE)
_SPLIT_RE = re.compile(r"(^[①-⑳]|^[0-9]+\.)", re.MULTILINE)


def is_large_clause(text: str) -> bool:
    """거대 조항(서브청킹 대상) 여부를 반환합니다.

    500자 초과 설계 원안(G_sub_chunk §1단계) 대신 실제 코퍼스 측정치 300자를
    임계값으로 사용합니다. 변경 시 이 상수만 수정하면 오프라인·런타임 모두 반영됩니다.
    """
    symbols = _SYMBOL_RE.findall(text)
    nums = _NUM_RE.findall(text)
    return len(text) > _LARGE_CLAUSE_CHAR_LIMIT or (len(symbols) + len(nums)) >= _LARGE_CLAUSE_SYMBOL_LIMIT


def split_into_sub_chunks(text: str) -> list[str]:
    """조항 텍스트를 항·호 기호 기준으로 분할합니다.

    거대 조항 조건 미달 시 원문 전체를 단일 원소 리스트로 반환합니다.
    빈 문자열 청크는 제외합니다.
    """
    if not is_large_clause(text):
        return [text]

    parts = _SPLIT_RE.split(text)

    chunks: list[str] = []

    # parts[0] 은 첫 기호 이전 선도 텍스트 (있을 수도 없을 수도)
    leading = parts[0].strip()
    if leading:
        chunks.append(leading)

    # 이후는 (기호, 내용) 쌍으로 반복
    for i in range(1, len(parts), 2):
        symbol = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        chunk = (symbol + body).strip()
        if chunk:
            chunks.append(chunk)

    return chunks if chunks else [text]
