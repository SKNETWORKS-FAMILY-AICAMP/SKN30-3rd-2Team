"""WorkShield 발표용 스트림릿 데모 앱 (MCP 클라이언트 연동판).

두 서버 체계:
    [터미널 1 · 루트]  just run-mcp streamable-http 8000   ← MCP 서버
    [터미널 2 · 루트]  uv run --project demo streamlit run demo/streamlit_app.py

연결 방식은 demo/src/config.py 의 APP_ENV 를 따른다.
    prod  (데모 기본) → Streamable HTTP 로 WORKSHIELD_MCP_URL 접속 (두 서버 체계)
    local             → stdio: 클라이언트가 MCP 서버를 서브프로세스로 직접 기동

파일 업로드는 필수이며, 실서버 호출 실패(서버 미기동·파이프라인 오류) 시에는
mock 으로 폴백하지 않고 에러 화면을 표시한다.

LLM 요약(_render_summary_cards)은 demo/src/llm 패키지를 통해 LLM_PROVIDER 가
구성돼 있으면 사고과정/요약을 스트리밍하고, 아니면 고정 문구(_STATIC_SUMMARY)를 사용한다.
"""

import asyncio
import base64
import logging
import os
import queue
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# demo/src 를 모듈 검색 경로에 추가 (config · workshield_mcp_client import 용)
DEMO_SRC = Path(__file__).resolve().parent / "src"
if str(DEMO_SRC) not in sys.path:
    sys.path.insert(0, str(DEMO_SRC))

# 데모 기본 연결 모드 = HTTP 두 서버 체계.
# (셸/.env 에서 APP_ENV 를 명시하면 그 값이 우선. local 로 바꾸면 stdio 자동 기동)
os.environ.setdefault("APP_ENV", "prod")

import streamlit as st
from pydantic import BaseModel, Field

from config import app_env, WORKSHIELD_MCP_URL
from workshield_mcp_client import WorkShieldMCPClient

# ──────────────────────────────────────────────────────────────
# 이탈 유형 상수 (서버 응답의 Deviation enum 값과 동일한 문자열)
# 데모는 MCP 응답(JSON)만 소비하므로 루트 contracts 패키지에 의존하지 않는다.
# ──────────────────────────────────────────────────────────────

DEV_NONE = "NONE"
DEV_CHANGED = "CHANGED"
DEV_MISSING = "MISSING"
DEV_EXTRA = "EXTRA"
DEV_NO_MATCH = "NO_MATCH"

# ──────────────────────────────────────────────────────────────
# 화면용 데이터 모델 — UI 는 이 모델만 바라본다
# ──────────────────────────────────────────────────────────────


class GroundingRef(BaseModel):
    """법령 근거 참조 (korean-law-mcp 결과)."""

    law_name: str
    article: str
    source: str = ""


class ClauseCard(BaseModel):
    """검토 결과 카드 1장."""

    title: str
    deviation: str
    confidence: Optional[float] = None
    body_user: Optional[str] = None
    """내 계약서 조항 본문 (좌우 비교용)"""
    body_std: Optional[str] = None
    """매칭된 표준조항 본문 (좌우 비교용)"""
    std_ref: Optional[str] = None
    """표준 출처 좌표 (파일 · 조번호)"""
    note: Optional[str] = None
    toxic_pattern: Optional[str] = None
    toxic_enums: list[str] = Field(default_factory=list)
    """독소패턴 원시 enum 값 목록 (사람이 읽는 제목은 _toxic_title_map() 으로 매핑)"""
    grounding: list[GroundingRef] = Field(default_factory=list)


class ReviewDemoResult(BaseModel):
    """화면에 뿌릴 검토 결과 전체."""

    contract_type: str
    total_user_clauses: int
    none_titles: list[str]
    """이탈 없음(NONE) 조항 제목 목록"""
    cards: list[ClauseCard]
    """CHANGED / MISSING / EXTRA / NO_MATCH 카드"""


# ──────────────────────────────────────────────────────────────
# 실서버 호출 (WorkShieldMCPClient 경유)
# ──────────────────────────────────────────────────────────────


class DemoServerError(RuntimeError):
    """실서버 검토 실패 — 에러 화면 전환 트리거용."""


# MCP 호출 제한 시간(초). 로컬 CPU 서버는 첫 호출에 모델 로드가 포함되므로 너무 짧게 잡지 말 것.
MCP_TIMEOUT_SEC = 300

# 서버 도달성 사전 확인 타임아웃(초). 짧게 — "꺼져 있음"을 빨리 판단하기 위함.
REACHABILITY_CHECK_SEC = 2.0


def _preflight_check() -> None:
    """HTTP 모드일 때, mcp 클라이언트를 열기 전에 TCP 레벨로 서버 도달성만 먼저 확인한다.

    이 체크를 생략하고 서버가 꺼진 채로 곧장 mcp 클라이언트를 열면, mcp SDK 의
    streamable_http_client(anyio 기반)가 "연결 실패 + 정리(cleanup)"가 겹치는 순간
    취소 범위(cancel scope)가 태스크 경계를 넘나들며 깨져 매우 지저분한 크래시
    (BaseExceptionGroup 안에 GeneratorExit)를 낸다 — asyncio.wait_for 유무와 무관하게
    재현되는 mcp/anyio/httpx 조합의 알려진 문제 유형. 순수 소켓 연결로 먼저 걸러내면
    이 버그 경로 자체를 타지 않는다.
    """
    if app_env == "local":
        return  # stdio 모드는 서브프로세스 기동이라 TCP 체크 대상이 아님
    parsed = urlparse(WORKSHIELD_MCP_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=REACHABILITY_CHECK_SEC):
            pass
    except OSError as e:
        raise DemoServerError(
            f"MCP 서버({host}:{port})에 연결할 수 없습니다 — 서버가 꺼져 있는지 확인하세요. ({e})"
        ) from e


def _mcp_call(coro_factory):
    """MCP 도구 한 개를 동기 방식으로 호출한다 (호출마다 세션 개폐).

    HTTP 모드에선 가볍지만, stdio 모드에선 호출마다 서버 서브프로세스를 새로
    기동하므로 느리다 — 데모 기본은 HTTP(두 서버 체계)라는 전제.
    타임아웃·연결 실패는 httpx 계층에서 일반 Exception 으로 올라오므로,
    호출부가 DemoServerError 로 잡아 에러 화면으로 전환한다.
    """
    _preflight_check()

    async def _run():
        async with WorkShieldMCPClient(read_timeout=MCP_TIMEOUT_SEC) as client:
            return await coro_factory(client)

    try:
        return asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001 — mcp/anyio 조합이 간헐적으로 BaseException 계열
        # (CancelledError, BaseExceptionGroup 등)을 흘려보낼 수 있어 최후 안전망으로 넓게 잡는다.
        raise DemoServerError(f"MCP 호출 중 예기치 않은 오류: {_snippet(str(e), 100)}") from e


def _snippet(text: str, limit: int = 22) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _convert_server_response(data: dict, contract_type: str) -> ReviewDemoResult:
    """서버 ReviewContractResponse(JSON dict) → 화면 모델 변환."""
    status = data.get("status")
    if status != "OK":
        raise DemoServerError(data.get("message") or f"서버 응답 상태 {status}")

    none_titles: list[str] = []
    cards: list[ClauseCard] = []
    user_clause_count = 0

    for item in data.get("results", []):
        deviation = item.get("deviation", DEV_NO_MATCH)
        user_clause = (item.get("user_clause") or "").strip()
        std = item.get("matched_standard") or {}
        std_title = (std.get("title") or "").strip()

        if deviation != DEV_MISSING:
            user_clause_count += 1

        if deviation == DEV_NONE:
            none_titles.append(std_title or _snippet(user_clause))
            continue

        if deviation == DEV_MISSING:
            title = f"표준 · {std_title}" if std_title else "표준 조항 (제목 없음)"
        else:
            title = std_title or _snippet(user_clause)

        # DeviationResult.toxic_patterns 는 ToxicPattern(str, Enum) 리스트이므로 JSON 직렬화 시
        # 순수 enum 값 문자열(예: "IP_TOTAL_FREE")로 온다. 혹시 dict 형태(예: {"pattern": "..."})로
        # 오는 경우까지 안전하게 대비해 pattern/value 키를 먼저 확인한다.
        toxic = item.get("toxic_patterns") or []
        toxic_enums = [
            (t.get("pattern") or t.get("value") or "") if isinstance(t, dict) else str(t)
            for t in toxic
        ]
        toxic_enums = [e for e in toxic_enums if e]
        toxic_str = ", ".join(toxic_enums)

        cards.append(
            ClauseCard(
                title=title,
                deviation=deviation,
                confidence=item.get("confidence"),
                body_user=user_clause or None,
                body_std=(std.get("text") or None) if deviation == DEV_CHANGED else None,
                std_ref=std.get("source") or None,
                toxic_pattern=toxic_str or None,
                toxic_enums=toxic_enums,
                grounding=[
                    GroundingRef(
                        law_name=g.get("법령명", ""),
                        article=g.get("조번호", ""),
                        source=g.get("출처", ""),
                    )
                    for g in item.get("grounding", [])
                ],
            )
        )

    return ReviewDemoResult(
        contract_type=contract_type,
        total_user_clauses=user_clause_count,
        none_titles=none_titles,
        cards=cards,
    )


_STATIC_SUMMARY = (
    "이 계약서는 저작권 귀속 조항(제12조)이 표준조항과 달라 검토 후보이며 "
    "[근거: 저작권법 제5조], 표준의 대금 지급 시기 조항에 대응하는 내용이 없습니다. "
    "제15조는 알려진 독소 패턴(저작권 전부 무상귀속)과 일치합니다. "
    "제17조는 표준·법령에서 근거를 찾지 못해 판단하지 않습니다."
)


def _summary_payload(result: ReviewDemoResult) -> dict:
    """LLM 요약 입력용 페이로드 — 검출 결과와 법령 근거만 포함(자체 해석 재료 차단)."""
    return {
        "contract_type": result.contract_type,
        "matched_no_review": result.none_titles,  # 표준과 일치 → 검토 불필요 (NO_MATCH 아님)
        "detections": [
            {
                "title": c.title,
                "deviation": c.deviation,
                "confidence": c.confidence,
                "user_excerpt": _snippet(c.body_user, 200) if c.body_user else None,
                "standard_excerpt": _snippet(c.body_std, 200) if c.body_std else None,
                "standard_source": c.std_ref,
                "toxic": c.toxic_pattern,
                "grounding": [{"law": g.law_name, "article": g.article} for g in c.grounding],
                "note": c.note,
            }
            for c in result.cards
        ],
    }


import re

def _format_markdown_for_display(text: str) -> str:
    """마크다운 리스트(*, -, 숫자) 앞에 빈 줄이 없으면 강제로 빈 줄을 삽입하여
    목록이 화면에 정상적으로 정돈되어 렌더링되도록 보정합니다.
    """
    if not text:
        return ""
    formatted = text.strip()
    formatted = re.sub(r'(?<!\n)\n([*-])\s', r'\n\n\1 ', formatted)
    formatted = re.sub(r'(?<!\n)\n(\d+\.)\s', r'\n\n\1 ', formatted)
    return f"""
    {formatted}
    """


def _render_summary_cards(result: ReviewDemoResult) -> None:
    """근거 기반 요약: 왼쪽 '사고 과정'(스트리밍) + 오른쪽 '근거 기반 요약'(스트리밍) 2카드.
    최초 1회만 LLM 을 실호출해 스트리밍하고, 결과를 job_token 별로 캐시해 재실행 시 정적 렌더한다.
    LLM 미설정·실패 시 정적 문구(_STATIC_SUMMARY)로 폴백한다."""
    key = st.session_state.get("job_token")
    cache = st.session_state.get("summary_cards") or {}

    col_t, col_s = st.columns(2, gap="medium")
    with col_t:
        st.caption("🧠 사고 과정 — LLM (생성 근거 추적용)")
        box_t = st.container(border=True, height=400)
        ph_t = box_t.empty()
    with col_s:
        st.caption("✨ 근거 기반 요약 — 검출 결과만 인용")
        box_s = st.container(border=True, height=400)
        ph_s = box_s.empty()

    # 캐시 히트 → 정적 렌더 (재실행 때마다 LLM 재호출 방지)
    if key in cache:
        thought, answer = cache[key]
        ph_t.markdown(_format_markdown_for_display(thought) or "_(사고 과정 없음)_")
        ph_s.markdown(_format_markdown_for_display(answer) or _STATIC_SUMMARY)
    else:
        thought, answer = "", ""
        try:
            import llm
            if llm.is_configured():
                t_parts, a_parts = [], []
                for channel, piece in llm.summarize_stream(_summary_payload(result)):
                    if channel == "thought":
                        t_parts.append(piece)
                        ph_t.markdown(_format_markdown_for_display("".join(t_parts)))
                    else:
                        a_parts.append(piece)
                        ph_s.markdown(_format_markdown_for_display("".join(a_parts)))
                thought, answer = "".join(t_parts).strip(), "".join(a_parts).strip()
            if not answer:  # 미설정 or 빈 응답
                answer = _STATIC_SUMMARY
                ph_s.markdown(_format_markdown_for_display(answer))
            if not thought:
                ph_t.markdown("_(사고 과정 없음)_")
        except Exception as e:
            logger.exception("LLM summary generation failed")
            answer = _STATIC_SUMMARY
            ph_t.markdown(f"_(요약 생성 실패 — {type(e).__name__}: {e})_")
            ph_s.markdown(_format_markdown_for_display(answer))
        cache[key] = (thought, answer)
        st.session_state.summary_cards = cache

    st.caption(
        "요약은 검출 결과와 법령 조문만 입력받아 생성되며, 자체 법률 해석을 만들지 않습니다. "
        "해석 고도화는 다음 프로젝트에서 진행 예정."
    )


# ──────────────────────────────────────────────────────────────
# 스타일 (HTML 목업의 파스텔 연보라 팔레트)
# ──────────────────────────────────────────────────────────────

PALETTE_CSS = """
<style>
  .stApp { background: #EDEFFA; }
  h1, h2, h3 { color: #3E4557; }
  div[data-testid="stExpander"] {
    background: #FFFFFF; border-radius: 14px;
    box-shadow: 0 1px 3px rgba(70,80,140,.06), 0 4px 14px rgba(70,80,140,.07);
  }
  .ws-tile { border-radius: 12px; padding: 10px; text-align: center;
             height: 92px; display: flex; flex-direction: column; justify-content: center; }
  .ws-tile .lbl { font-size: 12px; margin: 0; font-weight: 500; }
  .ws-tile .val { font-size: 20px; font-weight: 600; margin: 2px 0 0; }
  .ws-tile .sub { font-size: 10px; margin: 0; opacity: .75; }
  .ws-badge { display:inline-block; font-size:11px; font-weight:500;
              padding:2px 8px; border-radius:20px; margin-right:4px; }
  .ws-llm { border:1px dashed #C9CCE4; border-radius:14px; padding:14px 18px;
            background:#F2F3FB; color:#5F6779; font-size:14px; margin-bottom:16px; }
  .ws-step { border-left:2px solid #C9CCE4; margin-left:14px;
             padding:0 0 18px 20px; position:relative; }
  .ws-step .num { position:absolute; left:-15px; top:-2px; width:28px; height:28px;
                  border-radius:50%; background:#6E76F2; color:#fff; font-size:13px;
                  font-weight:600; display:flex; align-items:center; justify-content:center; }
  .ws-step .num.done { background:#5BB97F; }
  .ws-step p { margin:4px 0 0; font-size:13.5px; color:#5F6779; }
  .ws-step code { background:#F2F3FB; border-radius:6px; padding:2px 6px; font-size:12px; }
  /* 실시간 검토 단계 스피너 애니메이션 */
  @keyframes ws-spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  .ws-spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid #C9CCE4;
    border-radius: 50%;
    border-top-color: #6E76F2;
    animation: ws-spin 0.8s linear infinite;
    margin-left: 8px;
    vertical-align: middle;
  }
  /* 결과 그룹 카드 크기 통일: 접힌 헤더 높이 고정 + 펼친 본문 높이 고정(내부 스크롤) */
  div[data-testid="stExpander"] details summary { min-height: 52px; align-items: center; }
  div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
    height: 320px; overflow-y: auto;
  }
  /* bordered 컨테이너를 HTML 목업의 흰 카드처럼 */
  div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF; border-radius: 18px;
    box-shadow: 0 1px 3px rgba(70,80,140,.06), 0 4px 14px rgba(70,80,140,.07);
  }
  /* bordered 컨테이너 내 텍스트 가독성 향상 */
  div[data-testid="stVerticalBlockBorderWrapper"] p {
    font-size: 13.5px !important;
    line-height: 1.6 !important;
    color: #4F5568 !important;
  }
  div[data-testid="stVerticalBlockBorderWrapper"] li {
    font-size: 13.5px !important;
    line-height: 1.5 !important;
    margin-bottom: 4px;
    color: #4F5568 !important;
  }
</style>
"""

# 독소패턴 enum → 사람이 읽는 제목 정적 폴백 (서버 list_toxic_pattern_details 미기동 시 사용)
TOXIC_TITLES = {
    "NONCOMPETE_EXCESS": "과도한 경업금지 및 영업활동 제한",
    "IP_TOTAL_FREE": "저작권·지식재산권 전부 무상 귀속",
    "PAYMENT_DELAY_UNFAIR": "부당한 대금 지급 지연 및 지체상금 면제",
    "UNILATERAL_CHANGE": "일방적인 과업 범위 변경 권한",
    "UNFAIR_DAMAGE_CLAIM": "부당하게 과도한 손해배상 청구액 설정",
    "UNILATERAL_INTERPRETATION": "도급인의 일방적인 해석권",
    "UNILATERAL_CANCELLATION": "일방적인 계약 취소",
    "INDEFINITE_CONFIDENTIALITY": "불특정 기간 동안의 비밀유지 의무",
    "UNPAID_ADDITIONAL_WORK": "무보상 추가 업무 강요",
}

# 이탈 유형별 화면 메타: (라벨 점, 한 줄 설명, "배경색;글자색")
DEVIATION_META: dict[str, tuple[str, str, str]] = {
    DEV_NONE: ("🟢", "표준과 일치, 검토 후보 아님", "#E4F3E9;color:#2E7D4F"),
    DEV_CHANGED: ("🔵", "표준과 매칭됐지만 본문이 다른 조항", "#E7E9FD;color:#4F57C9"),
    DEV_MISSING: ("🔴", "표준에는 있는데 내 계약서에 없는 조항", "#F7E2E2;color:#B25454"),
    DEV_EXTRA: ("🟡", "표준에 없는 추가 조항 (독소 패턴 대조 포함)", "#FFF3D6;color:#8A6A1F"),
    DEV_NO_MATCH: ("⚪", "근거를 찾지 못해 판단하지 않은 조항", "#F2F3FB;color:#5F6779"),
}

# 파이프라인 단계: (MCP 도구 여부, 이름, 설명, 로그 예시)
PIPELINE_STEPS: list[tuple[bool, str, str, Optional[str]]] = [
    (True, "parse_contract", "계약서를 조항 단위로 분해",
     '[{"idx":1,"조번호":"제1조","title":"목적"}, {"idx":12,"조번호":"제12조","title":"저작권의 귀속"}, ...]'),
    (False, "embed", "각 조항을 dense 1024dim + sparse 표현으로 변환 (bge-m3)", None),
    (True, "match_clause", "하이브리드 검색으로 표준조항 top-5 추출 → 리랭커로 재정렬",
     "1. sw_std-art12  score 0.79 → 0.91 (재정렬 후 1위)\n2. sw_std-art14  score 0.81 → 0.63"),
    (False, "deviation", "매칭 확정 → 표준 본문과 차이 감지 → 이탈 판정 · 독소 패턴 대조", None),
    (True, "get_grounding", "korean-law-mcp 호출 → 관련 법령 조문 조회", None),
    (True, "review_contract", "조항별 최종 응답(매칭·이탈·근거) 조립 완료 → 상단 「검토 결과」에 표시", None),
]

# 계약 유형: MVP 활성 3종 (값은 서버 ContractType enum 문자열과 동일) + 추후 업데이트 예정
ACTIVE_TYPES: dict[str, str] = {
    "SW 프리랜서 표준계약서 (SW_FREELANCE)": "SW_FREELANCE",
    "상용SW 공급·개발·구축 하도급 (SI_SUBCONTRACT)": "SI_SUBCONTRACT",
    "상용SW 유지관리 하도급 (SM_SUBCONTRACT)": "SM_SUBCONTRACT",
}
FUTURE_TYPES = ["방송산업", "만화산업", "영화산업", "건설산업", "프리랜서 강사"]


# ──────────────────────────────────────────────────────────────
# 렌더링
# ──────────────────────────────────────────────────────────────


def _badge(text: str, style: str) -> str:
    return f'<span class="ws-badge" style="background:{style}">{text}</span>'


def _toxic_title_map() -> dict:
    """독소패턴 enum → 제목 매핑. 서버 조회를 best-effort 로 시도하고 정적 폴백과 병합, 세션에 캐시."""
    cached = st.session_state.get("toxic_titles")
    if cached is not None:
        return cached
    titles = dict(TOXIC_TITLES)
    try:
        data = _mcp_call(lambda c: c.list_toxic_pattern_details())
        for row in (data or {}).get("patterns", []):
            if row.get("pattern") and row.get("title"):
                titles[row["pattern"]] = row["title"]
    except Exception:
        pass  # 서버 미기동이면 정적 폴백(TOXIC_TITLES) 사용
    st.session_state.toxic_titles = titles
    return titles


def render_sidebar() -> None:
    """데모 소개 + 연결 상태 사이드바 (접기 가능)."""
    with st.sidebar:
        st.markdown("### 🛡️ 이 데모는")
        st.markdown(
            "프리랜서 용역계약서를 표준계약서와 **조항 단위로 비교**해 이탈(누락·추가·변경)을 "
            "탐지하고, 모든 결과에 표준조항·법령 출처를 붙여 반환하는 RAG 파이프라인 데모입니다."
        )
        st.markdown(
            "근거가 없는 항목은 판단하지 않습니다 — 매칭 실패는 빈 응답 대신 "
            "**NO_MATCH 명시 표식**으로 반환됩니다."
        )
        st.caption('모든 결과는 "검토가 필요한 후보"이며, 위법·불리함을 단정하지 않습니다.')
        st.divider()
        st.markdown("**연결 상태**")
        if app_env == "local":
            st.caption("stdio — 검토 시 MCP 서버를 서브프로세스로 자동 기동")
        else:
            st.caption(f"HTTP — {WORKSHIELD_MCP_URL}")
            st.caption("서버 실행: `just run-mcp streamable-http 8000`")
        source = st.session_state.get("data_source")
        if source:
            st.caption(f"최근 검토 데이터: {source}")


def render_form() -> None:
    """검토 시작 카드: 업로드 + 계약 유형 + 서버 구성 (통합, 흰 카드)."""
    st.markdown("##### 검토 시작")
    with st.container(border=True):
        left, right = st.columns([1.1, 1], gap="large")

        with left:
            uploaded = st.file_uploader(
                "계약서 업로드 (필수)",
                type=["pdf", "hwp", "hwpx", "doc", "docx"],
                help="PDF · HWP · WORD 파일 (스캔 이미지 제외)",
            )
            st.caption("🔒 업로드된 계약서 파일은 저장하지 않으며, 검토가 끝나면 즉시 파기됩니다.")
            if uploaded is not None:
                st.caption(f"📄 {uploaded.name} · {uploaded.size:,} bytes — 실서버로 검토합니다.")
            else:
                st.caption("⚠️ 검토할 계약서 파일을 업로드해야 시작할 수 있습니다.")

            options = list(ACTIVE_TYPES.keys()) + [
                f"{t} 표준계약서 — 추후 업데이트 예정" for t in FUTURE_TYPES
            ]
            type_label = st.selectbox("표준계약 유형", options)
            is_future = type_label not in ACTIVE_TYPES
            if is_future:
                st.warning("이 유형은 추후 업데이트 예정입니다. 현재 지원 중인 유형을 선택해 주세요.", icon="🚧")

            already_run = st.session_state.phase in ("done", "error")
            if st.button(
                "다시 검토" if already_run else "표준 대비 검토 시작",
                type="primary",
                use_container_width=True,
                disabled=is_future,
            ):
                st.session_state.upload_bytes = uploaded.getvalue()
                st.session_state.upload_name = uploaded.name
                st.session_state.contract_type = ACTIVE_TYPES[type_label]
                st.session_state.job_token = time.time()  # 재실행 가드용 실행 식별자
                st.session_state.phase = "running"
                st.rerun()

        with right:
            st.markdown("**서버 구성 사양**")
            rows = [
                ("임베딩 모델", "bge-m3", "조합"),
                ("리랭커", "bge-reranker-v2-m3", "조합"),
                ("RDB (SQLite)", "표준조항 273건 적재 (4종·판본별)", None),
                ("벡터 DB (Chroma)", "서브청크 1,898건 · dense+sparse", None),
                ("독소조항 패턴셋", "40건 큐레이션", "직접 구축"),
                ("korean-law-mcp", "연동됨", "조합"),
                ("이탈 탐지 로직 · 스키마", "", "직접 구축"),
            ]
            for name, value, tag in rows:
                badge = ""
                if tag == "조합":
                    badge = _badge("조합", "#DDEEFB;color:#2E6E9E")
                elif tag == "직접 구축":
                    badge = _badge("직접 구축", "#E7E9FD;color:#4F57C9")
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:7px 0;'
                    f'border-bottom:0.5px solid #E3E5F2;font-size:14px;color:#3E4557">'
                    f"<span>{name}</span><span>{value} {badge}</span></div>",
                    unsafe_allow_html=True,
                )


def _render_step_status(idx: int, is_tool: bool, name: str, desc: str, mono: Optional[str], status: str) -> None:
    if status == "done":
        num = '<div class="num done">✓</div>'
    elif status == "running":
        num = f'<div class="num">{idx}</div>'
    else:  # pending
        num = f'<div class="num" style="background:#C9CCE4;color:#7A7F99">{idx}</div>'

    badge = (
        _badge(name, "#DDEEFB;color:#2E6E9E") if is_tool
        else _badge(name, "#F2F3FB;color:#5F6779")
    )
    
    # 현재 실행 중("running")이면 배지 옆에 실시간 회전 스피너 추가
    spinner_html = '<span class="ws-spinner"></span>' if status == "running" else ""
    
    mono_html = f"<p><code>{mono}</code></p>" if mono else ""
    st.markdown(
        f'<div class="ws-step">{num}{badge}{spinner_html}<p>{desc}</p>{mono_html}</div>',
        unsafe_allow_html=True,
    )


def get_steps_status(current_phase_msg: str, done_total: Optional[tuple[int, int]] = None) -> list[dict]:
    # Returns list of 6 dicts with keys: is_tool, name, desc, mono, status
    steps = [
        {"is_tool": True, "name": "parse_contract", "desc": "계약서를 조항 단위로 분해", "mono": None, "status": "pending"},
        {"is_tool": False, "name": "embed", "desc": "각 조항을 dense 1024dim + sparse 표현으로 변환 (bge-m3)", "mono": None, "status": "pending"},
        {"is_tool": True, "name": "match_clause", "desc": "하이브리드 검색으로 표준조항 top-5 추출 → 리랭커로 재정렬", "mono": None, "status": "pending"},
        {"is_tool": False, "name": "deviation", "desc": "매칭 확정 → 표준 본문과 차이 감지 → 이탈 판정 · 독소 패턴 대조", "mono": None, "status": "pending"},
        {"is_tool": True, "name": "get_grounding", "desc": "korean-law-mcp 호출 → 관련 법령 조문 조회", "mono": None, "status": "pending"},
        {"is_tool": True, "name": "review_contract", "desc": "조항별 최종 응답(매칭·이탈·근거) 조립 완료 → 상단 「검토 결과」에 표시", "mono": None, "status": "pending"},
    ]
    
    # Check current state based on message substring
    if "준비" in current_phase_msg:  # PREPARE
        steps[0]["status"] = "running"
    elif "검색" in current_phase_msg:  # BATCH_SEARCH
        steps[0]["status"] = "done"
        steps[1]["status"] = "running"
        steps[2]["status"] = "running"
    elif "재정렬" in current_phase_msg:  # RERANK
        steps[0]["status"] = "done"
        steps[1]["status"] = "done"
        steps[2]["status"] = "done"
        steps[3]["status"] = "running"
    elif "분류" in current_phase_msg:  # CLAUSE_REVIEW
        steps[0]["status"] = "done"
        steps[1]["status"] = "done"
        steps[2]["status"] = "done"
        steps[3]["status"] = "running"
        if done_total:
            steps[3]["desc"] = f"매칭 확정 → 표준 본문과 차이 감지 → 이탈 판정 · 독소 패턴 대조 ({done_total[0]}/{done_total[1]})"
    elif "누락" in current_phase_msg or "분석" in current_phase_msg:  # MISSING_DETECTION
        steps[0]["status"] = "done"
        steps[1]["status"] = "done"
        steps[2]["status"] = "done"
        steps[3]["status"] = "done"
        steps[4]["status"] = "running"
        steps[5]["status"] = "running"
    elif "완료" in current_phase_msg or current_phase_msg == "DONE":
        for s in steps:
            s["status"] = "done"
            
    return steps


def run_review_pipeline_with_progress(
    file_bytes: bytes,
    file_name: str,
    contract_type: str,
    progress_placeholder,
) -> tuple[ReviewDemoResult, str]:
    q = queue.Queue()
    b64 = base64.b64encode(file_bytes).decode("ascii")

    def _worker():
        async def progress_cb(progress, total, message):
            q.put(("progress", progress, total, message))

        async def _run():
            async with WorkShieldMCPClient(read_timeout=MCP_TIMEOUT_SEC) as client:
                return await client.review_contract(
                    contract_type=contract_type,
                    file_content=b64,
                    file_name=file_name,
                    progress_callback=progress_cb,
                )
        try:
            _preflight_check()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(_run())
            q.put(("done", res))
        except Exception as e:
            q.put(("error", e))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    last_msg = "검토 준비 중..."
    last_done_total = None

    # Loop to poll the queue
    while True:
        try:
            msg_type, *args = q.get(timeout=0.1)
        except queue.Empty:
            continue

        if msg_type == "progress":
            progress_val, total_val, msg = args
            last_msg = msg or last_msg
            if total_val and total_val > 0:
                last_done_total = (int(progress_val), int(total_val))
            
            # Update the steps rendering
            steps = get_steps_status(last_msg, last_done_total)
            with progress_placeholder.container(border=True):
                st.caption(
                    "계약서 한 부가 결과로 나오기까지 실행되는 단계 — "
                    + _badge("MCP 도구", "#DDEEFB;color:#2E6E9E")
                    + _badge("내부 단계", "#F2F3FB;color:#5F6779"),
                    unsafe_allow_html=True,
                )
                if last_done_total:
                    done, total = last_done_total
                    st.progress(min(1.0, done / total))
                with st.empty().container():
                    for i, s in enumerate(steps):
                        _render_step_status(i + 1, s["is_tool"], s["name"], s["desc"], s["mono"], s["status"])
                        
        elif msg_type == "done":
            data = args[0]
            if data.get("status") == "ERROR":
                raise DemoServerError(data.get("message", "MCP 호출 실패"))
            
            # Finalize: render all checkmarks
            steps = get_steps_status("DONE")
            with progress_placeholder.container(border=True):
                st.caption(
                    "계약서 한 부가 결과로 나오기까지 실행되는 단계 — "
                    + _badge("MCP 도구", "#DDEEFB;color:#2E6E9E")
                    + _badge("내부 단계", "#F2F3FB;color:#5F6779"),
                    unsafe_allow_html=True,
                )
                st.progress(1.0)
                with st.empty().container():
                    for i, s in enumerate(steps):
                        _render_step_status(i + 1, s["is_tool"], s["name"], s["desc"], s["mono"], "done")
            
            # Save the final steps to session_state so they can be re-rendered in done phase
            st.session_state.live_steps = [(s["is_tool"], s["name"], s["desc"], s["mono"]) for s in steps]
            return _convert_server_response(data, contract_type), f"실서버 ({app_env})"
            
        elif msg_type == "error":
            raise args[0]


def render_pipeline() -> None:
    """파이프라인 진행 로그 (완료 화면에서 최근 실행 로그 재표시. 세션의 live_steps 우선)."""
    steps = st.session_state.get("live_steps") or PIPELINE_STEPS
    st.markdown("##### 파이프라인 진행 로그")
    with st.container(border=True):
        st.caption(
            "계약서 한 부가 결과로 나오기까지 실행되는 단계 — "
            + _badge("MCP 도구", "#DDEEFB;color:#2E6E9E")
            + _badge("내부 단계", "#F2F3FB;color:#5F6779"),
            unsafe_allow_html=True,
        )
        for i, (is_tool, name, desc, mono) in enumerate(steps):
            _render_step_status(i + 1, is_tool, name, desc, mono, status="done")


def render_results(result: ReviewDemoResult) -> None:
    """검토 결과: LLM 요약 → 프레이밍 안내 → 요약 밴드 → 유형별 그룹(가로 나열)."""
    st.markdown("##### 검토 결과")
    source = st.session_state.get("data_source")
    if source:
        st.caption(f"데이터 출처: {source}")

    # LLM 근거 기반 요약 — 사고 과정 + 요약 2카드 스트리밍 (검토 결과 바로 아래)
    _render_summary_cards(result)

    st.info("아래 결과는 **검토가 필요한 후보**를 표시한 것이며, 위법·불리함을 단정하지 않습니다.", icon="ℹ️")

    tmap = _toxic_title_map()
    by_dev: dict[str, list[ClauseCard]] = {d: [] for d in DEVIATION_META}
    for card in result.cards:
        by_dev.setdefault(card.deviation, []).append(card)
    counts = {
        DEV_NONE: len(result.none_titles),
        **{d: len(cards) for d, cards in by_dev.items() if d != DEV_NONE},
    }

    if "selected_dev" not in st.session_state:
        st.session_state.selected_dev = DEV_CHANGED

    # 좌우 분할 컨테이너
    with st.container():
        st.markdown('<div id="results-tab-marker"></div>', unsafe_allow_html=True)
        left_col, right_col = st.columns([1.3, 3.7], gap="medium")

        # 1. 좌측 세로 탭 버튼 목록
        with left_col:
            st.markdown("<p style='font-weight:600; font-size:14px; margin-bottom:10px; text-align: center;'>이탈 유형 목록</p>", unsafe_allow_html=True)
            for dev in DEVIATION_META:
                dot, desc, style_str = DEVIATION_META[dev]
                count = counts.get(dev, 0)
                label = f"{dot} {dev} ({count}건)"
                if st.button(label, key=f"tab_{dev}"):
                    st.session_state.selected_dev = dev
                    st.rerun()

        # 2. 우측 상세 내용 영역
        with right_col:
            selected_dev = st.session_state.selected_dev
            dot, desc, style_str = DEVIATION_META[selected_dev]
            
            # 스타일 헤더 (고정)
            bg_color = style_str.split(";")[0].split(":")[1] if "background" in style_str else "#F2F3FB"
            text_color = style_str.split(";")[1].split(":")[1] if "color" in style_str else "#5F6779"
            
            st.markdown(
                f'<div style="background:{bg_color}; padding:14px; border-radius:10px; margin-bottom:15px;'
                f'border-left:5px solid {text_color}">'
                f'<h4 style="margin:0; color:{text_color}; font-weight:600;">{dot} {selected_dev}</h4>'
                f'<p style="margin:5px 0 0; font-size:13px; color:{text_color}; opacity:0.85;">{desc}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # 상세 카드 목록만 스크롤되도록 고정 높이 컨테이너 배치 (border=False)
            with st.container(height=600, border=False):
                if selected_dev == DEV_NONE:
                    if result.none_titles:
                        st.markdown("##### 일치하는 조항 목록")
                        st.markdown(" · ".join(result.none_titles))
                    else:
                        st.info("일치하는 표준 조항이 없습니다.", icon="ℹ️")
                else:
                    cards = by_dev.get(selected_dev, [])
                    if not cards:
                        st.info("해당 이탈 유형의 조항이 없습니다.", icon="ℹ️")
                    else:
                        for card in cards:
                            st.markdown(f"##### {card.title}")
                            if card.confidence is not None and card.deviation != DEV_MISSING:
                                st.caption(f"신뢰도 {card.confidence:.2f}")
                            if card.toxic_enums:
                                labels = ", ".join(f"{tmap.get(e, e)} · {e}" for e in card.toxic_enums)
                                st.error(f"독소 패턴 · {labels}", icon="⚠️")
                            elif card.toxic_pattern:
                                st.error(f"독소 패턴 · {card.toxic_pattern}", icon="⚠️")
                            
                            if card.body_user and card.body_std:
                                comp_col_left, comp_col_right = st.columns(2, gap="small")
                                with comp_col_left:
                                    st.caption("✍️ 내 계약서")
                                    st.info(card.body_user)
                                with comp_col_right:
                                    st.caption("📜 표준조항")
                                    st.success(card.body_std)
                            elif card.body_user:
                                st.caption("✍️ 내 계약서")
                                st.info(card.body_user)
                            
                            if card.note:
                                st.markdown(f"💡 **참고**: {card.note}")
                            
                            for g in card.grounding:
                                st.caption(f"⚖️ 근거: {g.law_name} {g.article} ({g.source})")
                            if card.std_ref:
                                st.caption(f"표준 출처: {card.std_ref}")
                            st.divider()

    # Dynamic CSS Injection
    DEVIATION_THEMES = {
        DEV_NONE: {"bg": "#E4F3E9", "text": "#2E7D4F", "border": "#2E7D4F"},
        DEV_CHANGED: {"bg": "#E7E9FD", "text": "#4F57C9", "border": "#4F57C9"},
        DEV_MISSING: {"bg": "#F7E2E2", "text": "#B25454", "border": "#B25454"},
        DEV_EXTRA: {"bg": "#FFF3D6", "text": "#8A6A1F", "border": "#8A6A1F"},
        DEV_NO_MATCH: {"bg": "#F2F3FB", "text": "#5F6779", "border": "#5F6779"},
    }

    css_rules = []
    css_rules.append("""
    /* 좌측 세로 탭 버튼의 전체 컨테이너와 stButton의 가로 넓이를 100%로 강제 통일하되, 배경/패딩/그림자는 주지 않음 */
    div[data-testid="stVerticalBlock"]:has(#results-tab-marker) div[data-testid="stColumn"]:first-child div.element-container,
    div[data-testid="stVerticalBlock"]:has(#results-tab-marker) div[data-testid="stColumn"]:first-child div.stButton {
        width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    /* 실제 버튼 요소에만 가로 100% 넓이 및 정렬, 패딩, 보더, 배경색, 그림자 스타일 적용 */
    div[data-testid="stVerticalBlock"]:has(#results-tab-marker) div[data-testid="stColumn"]:first-child button {
        width: 100% !important;
        text-align: left !important;
        padding: 14px 18px !important;
        border-radius: 12px !important;
        font-size: 13.5px !important;
        margin-bottom: 8px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        box-shadow: 0 1px 3px rgba(70,80,140,.06), 0 4px 12px rgba(70,80,140,.05) !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stVerticalBlock"]:has(#results-tab-marker) div[data-testid="stColumn"]:first-child button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(70,80,140,0.12) !important;
    }
    """)

    for idx, dev in enumerate(DEVIATION_META):
        theme = DEVIATION_THEMES[dev]
        is_active = (st.session_state.selected_dev == dev)
        
        if is_active:
            css_rules.append(f"""
            div[data-testid="stVerticalBlock"]:has(#results-tab-marker) div[data-testid="stColumn"]:first-child div.element-container:nth-child({idx+2}) button {{
                background-color: {theme['bg']} !important;
                color: {theme['text']} !important;
                border: 2px solid {theme['border']} !important;
                font-weight: bold !important;
            }}
            """)
        else:
            css_rules.append(f"""
            div[data-testid="stVerticalBlock"]:has(#results-tab-marker) div[data-testid="stColumn"]:first-child div.element-container:nth-child({idx+2}) button {{
                background-color: #FFFFFF !important;
                color: #5F6779 !important;
                border: 1px solid #E3E5F2 !important;
            }}
            """)

    st.markdown(f"<style>{''.join(css_rules)}</style>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 메인 플로우: idle → running(로그 연출 + 실서버 호출) → done(결과가 위로 쌓임)
# ──────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="WorkShield — 프리랜서 계약서 검토",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="collapsed",  # 데모 소개·연결 상태는 접힌 사이드바에
    )
    st.markdown(PALETTE_CSS, unsafe_allow_html=True)

    if "phase" not in st.session_state:
        st.session_state.phase = "idle"

    render_sidebar()
    st.title("WorkShield — 프리랜서 계약서 검토 서비스 데모")
    st.caption("내부 시연용 · 사용자 서비스 화면 아님")

    phase: str = st.session_state.phase

    if phase == "done":
        # 완료: 결과가 맨 위, 로그가 그 아래, 검토 시작 카드는 맨 아래로 밀림
        render_results(st.session_state.result)
        st.divider()
        render_pipeline()
        st.divider()
        render_form()

    elif phase == "error":
        # 실패: 에러 배너가 맨 위, 재시도는 아래 검토 시작 카드에서
        st.error(
            f"검토에 실패했습니다 — {st.session_state.get('error_message', '알 수 없는 오류')}",
            icon="🚨",
        )
        if st.session_state.get("live_steps"):
            st.divider()
            render_pipeline()
        st.divider()
        render_form()

    elif phase == "running":
        # 재실행 가드: 검토 중 화면 조작으로 스크립트가 재시작돼도,
        # 이미 끝난 실행(job_token 일치)이면 다시 돌지 않고 그 결과 화면으로 직행
        token = st.session_state.get("job_token")
        if token is not None and st.session_state.get("done_token") == token:
            st.session_state.phase = st.session_state.get("resolved_phase", "done")
            st.rerun()

        # 실행 중: 로그를 최상단에 단독 배치 → 단계가 하나씩 뜨는 것이 바로 보임
        st.caption("⏳ 검토 중 — 파이프라인이 순서대로 실행됩니다")
        file_bytes = st.session_state.get("upload_bytes")
        file_name = st.session_state.get("upload_name")
        contract_type = st.session_state.get("contract_type", "SW_FREELANCE")

        st.session_state.live_steps = None
        progress_placeholder = st.empty()
        try:
            result, source = run_review_pipeline_with_progress(
                file_bytes, file_name, contract_type, progress_placeholder
            )
        except Exception as e:
            st.session_state.error_message = _snippet(str(e), 200)
            st.session_state.done_token = token
            st.session_state.resolved_phase = "error"
            st.session_state.phase = "error"
            st.rerun()

        st.session_state.result = result
        st.session_state.data_source = source
        st.session_state.done_token = token
        st.session_state.resolved_phase = "done"
        st.session_state.phase = "done"
        time.sleep(0.8)  # 마지막 ✓ 단계가 눈에 들어올 여유
        st.rerun()

    else:  # idle
        render_form()

    st.caption("WorkShield 1차 MVP · 시연용 데모 (평가 수치는 골든셋 확정 후 반영)")


main()
