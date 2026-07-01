from enum import Enum

class ContractType(str, Enum):
    SW_FREELANCE = "SW_FREELANCE"
    """SW 프리랜서 (도급/용역)"""
    SI_SUBCONTRACT = "SI_SUBCONTRACT"
    """상용소프트웨어 공급개발구축업 (하도급)"""
    SM_SUBCONTRACT = "SM_SUBCONTRACT"
    """상용소프트웨어 유지관리업종 (하도급)"""

    # todo: 1차 도입 검토 필요
    SW_EMPLOYMENT = "SW_EMPLOYMENT"
    """SW 종사자 (기간제/단시간 근로)"""

    # -- 아래는 mvp에 포함하지 않음 --
    # SW_NDA = "SW_NDA"
    # """소프트웨어사업 표준 비밀유지계약서"""
    # SW_DIRECT_PAYMENT = "SW_DIRECT_PAYMENT"
    # """하도급대금 직접지급 합의서"""
    # SW_MODIFICATION = "SW_MODIFICATION"
    # """표준약식변경 하도급계약서"""
    # SW_INDEXATION = "SW_INDEXATION"
    # """표준 연동계약서 (하도급대금 연동 계약서)"""
    # ARTS_SERVICE = "ARTS_SERVICE"
    # """문화예술용역"""

class Category(str, Enum):
    def __new__(cls, value, description, anchors):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.description = description
        obj.anchors = anchors
        return obj

    # ── 계약서 공통 ──────────────────────────────
    PAYMENT = (
        "PAYMENT",
        "대금지급 / 임금",
        ["보수 지급", "대금 지급", "임금", "지급 시기", "지급 방법", "보수 금액"],
    )
    IP_OWNERSHIP = (
        "IP_OWNERSHIP",
        "저작권/지식재산권 귀속 (2차적저작물 포함)",
        ["지식재산권 귀속", "저작권 귀속", "2차적저작물", "특허권", "결과물 소유권"],
    )
    SCOPE_SOW = (
        "SCOPE_SOW",
        "과업범위 / 담당업무",
        ["업무 범위", "담당 업무", "과업 내용", "업무 내용", "작업 범위", "수행 업무"],
    )
    CONTRACT_PERIOD = (
        "CONTRACT_PERIOD",
        "계약기간 / 근로계약기간",
        ["계약 기간", "근로계약 기간", "계약 유효기간", "업무 착수일", "업무 종료일", "근로 개시일"],
    )
    TERMINATION = (
        "TERMINATION",
        "계약해지 및 해제",
        ["계약 해지", "계약 해제", "계약 종료", "해지 사유", "해제 조건"],
    )
    CONFIDENTIALITY = (
        "CONFIDENTIALITY",
        "비밀유지 / 비밀준수",
        ["비밀 유지", "비밀 준수", "영업비밀", "기밀 정보", "비밀 보호"],
    )
    LIABILITY = (
        "LIABILITY",
        "손해배상 및 책임",
        ["손해배상", "배상 책임", "손해 배상 청구", "귀책사유", "배상 범위"],
    )
    DISPUTE = (
        "DISPUTE",
        "분쟁해결 및 관할법원",
        ["분쟁 해결", "관할 법원", "중재", "조정", "소송 관할"],
    )
    SOCIAL_INSURANCE = (
        "SOCIAL_INSURANCE",
        "사회보험 가입",
        ["사회보험", "국민연금", "건강보험", "고용보험", "산재보험"],
    )

    # ── 근로계약서 특화 ─────────────────────────────
    WORKING_HOURS = (
        "WORKING_HOURS",
        "근로 및 휴게시간",
        ["근로시간", "휴게시간", "소정근로", "연장근로", "야간근로", "시업 종업"],
    )
    HOLIDAY_LEAVE = (
        "HOLIDAY_LEAVE",
        "휴일 및 연차유급휴가",
        ["연차유급휴가", "휴일", "주휴일", "연차 휴가", "유급 휴가"],
    )

    # ── 도급계약서 특화 ─────────────────────────────
    DELIVERY_INSPECTION = (
        "DELIVERY_INSPECTION",
        "납품 및 검수",
        ["납품", "납기일", "검수", "수령 확인", "검사 기준", "계약목적물"],
    )
    WARRANTY = (
        "WARRANTY",
        "하자담보",
        ["하자담보", "하자보수", "하자 책임", "결함 보증", "하자보증"],
    )
    SUBCONTRACTING = (
        "SUBCONTRACTING",
        "재하도급 금지",
        ["재하도급", "재위탁", "하도급 금지", "제3자 위탁"],
    )

    # ── 공통 일반(캐치올) ────────────────────────────
    # 정의·효력발생 시점·통지 방법·계약서 해석 우선순위 등 특정 카테고리에 속하지 않는
    # 일반 조항. 앵커가 비어 있어 임베딩 점수 경쟁에 참여하지 않으며, 어느 카테고리와도
    # 유사도가 낮을 때의 명시적 fallback 으로만 사용한다. (drop/None 금지)
    # 법령 grounding·의존성 그래프 대상이 아니다.
    GENERAL = (
        "GENERAL",
        "일반 조항 (정의·효력·통지·해석 등)",
        [],
    )

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
    UNILATERAL_INTERPRETATION = "UNILATERAL_INTERPRETATION"
    """도급인의 일방적인 해석권"""
    UNILATERAL_CANCELLATION = "UNILATERAL_CANCELLATION"
    """일방적인 계약 취소"""
    INDEFINITE_CONFIDENTIALITY = "INDEFINITE_CONFIDENTIALITY"
    """불특정 기간 동안의 비밀유지 의무"""
    UNPAID_ADDITIONAL_WORK = "UNPAID_ADDITIONAL_WORK"
    """무보상 추가 업무 강요"""

class EdgeRelation(str, Enum):
    DEPENDS_ON = "DEPENDS_ON"
    """A조항의 변경이 B조항에 의존함"""
    RISK_PROPAGATION = "RISK_PROPAGATION"
    """A조항 이탈 시 B조항도 함께 검토 대상이 됨"""
