from enum import Enum

class ContractType(str, Enum):
    SW_FREELANCE = "SW_FREELANCE"
    """SW 프리랜서 (도급/용역)"""
    SW_EMPLOYMENT = "SW_EMPLOYMENT"
    """SW 종사자 (기간제/단시간 근로)"""
    ARTS_SERVICE = "ARTS_SERVICE"
    """문화예술용역"""

class Category(str, Enum):
    PAYMENT = "PAYMENT"
    """대금지급 / 임금"""
    IP_OWNERSHIP = "IP_OWNERSHIP"
    """저작권/지식재산권 귀속"""
    DERIVATIVE_WORK = "DERIVATIVE_WORK"
    """2차적저작물 작성권"""
    SCOPE_SOW = "SCOPE_SOW"
    """과업범위 / 담당업무"""
    TERMINATION = "TERMINATION"
    """계약해지 및 해제"""
    CONFIDENTIALITY = "CONFIDENTIALITY"
    """비밀유지 / 비밀준수"""
    LIABILITY = "LIABILITY"
    """손해배상 및 책임"""
    DISPUTE = "DISPUTE"
    """분쟁해결 및 관할법원"""
    
    # 근로계약서 대응용 (확장 카테고리)
    WORKING_HOURS = "WORKING_HOURS"
    """근로 및 휴게시간"""
    HOLIDAY_LEAVE = "HOLIDAY_LEAVE"
    """휴일 및 연차유급휴가"""
    SOCIAL_INSURANCE = "SOCIAL_INSURANCE"
    """사회보험 가입"""

class Deviation(str, Enum):
    MISSING = "MISSING"
    """누락"""
    EXTRA = "EXTRA"
    """추가 (표준 외 독소 또는 추가 조항)"""
    CHANGED = "CHANGED"
    """변경 (내용 차이 큼)"""
    NONE = "NONE"
    """이탈 없음 (일치)"""
    NO_MATCH = "NO_MATCH"
    """매칭 조항 없음 (4.2 실패 없음 규약 명시 표식)"""

class ToxicPattern(str, Enum):
    NONCOMPETE_EXCESS = "NONCOMPETE_EXCESS"
    """과도한 경업금지 및 영업활동 제한"""
    IP_TOTAL_FREE = "IP_TOTAL_FREE"
    """저작권/지식재산권 전부 무상 귀속 요구"""
    PAYMENT_DELAY_UNFAIR = "PAYMENT_DELAY_UNFAIR"
    """부당한 대금 지급 지연 및 지체상금 면제"""
    UNILATERAL_CHANGE = "UNILATERAL_CHANGE"
    """일방적인 과업 범위 변경 권한"""
    UNFAIR_DAMAGE_CLAIM = "UNFAIR_DAMAGE_CLAIM"
    """부당하게 과도한 손해배상 청구액 설정"""

class EdgeRelation(str, Enum):
    DEPENDS_ON = "DEPENDS_ON"
    """A조항의 변경이 B조항에 의존함"""
    RISK_PROPAGATION = "RISK_PROPAGATION"
    """A조항 이탈 시 B조항도 함께 검토 대상이 됨"""
