class EmptyDocumentError(ValueError):
    """파싱 결과 조항이 0건 — 스캔 PDF이거나 '제N조' 형식 없음"""

class CorpusUnavailableError(ValueError):
    """해당 contract_type의 표준 코퍼스가 DB에 없음 — 비교 명제 불성립"""

class InvalidConfigError(ValueError):
    """임계값 등 설정값의 의미적 불변식 위반 (예: match_threshold > change_threshold)"""

class PipelineIntegrityError(RuntimeError):
    """입력 조항 수 != 출력 조항 수 — NO_MATCH 누락 등 파이프라인 버그"""
