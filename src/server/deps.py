"""server 레이어의 의존성 조립(composition root).

도구 함수들이 구체 어댑터를 모듈 로드 시점에 직접 생성(eager 싱글턴)하지 않고,
포트(Parser/Grounder) 인스턴스를 이 프로바이더에서 받아 쓰도록 한다.

- **지연 생성**: 첫 사용 시점까지 생성을 미뤄, server/테스트 import가 어댑터 생성에
  묶이지 않게 한다(import-time 부작용·실패 결합 완화).
- **주입 가능**: `set_parser`/`set_grounder`로 테스트·배포별 구현을 교체할 봉합선을
  제공한다(헥사고날 DI 원칙 — 외부 작업은 코어/조립부에 주입).

streamable-http 동시 요청에서 최초 생성이 겹치지 않도록 락으로 보호한다.
"""

import threading
from typing import Optional

from contracts.ports import Parser, Grounder
from contracts.implement import KordocParser, KoreanLawGrounder

_lock = threading.Lock()
_parser: Optional[Parser] = None
_grounder: Optional[Grounder] = None


def get_parser() -> Parser:
    """Parser 포트 인스턴스를 반환한다(없으면 기본 어댑터를 지연 생성)."""
    global _parser
    if _parser is None:
        with _lock:
            if _parser is None:
                _parser = KordocParser()
    return _parser


def get_grounder() -> Grounder:
    """Grounder 포트 인스턴스를 반환한다(없으면 기본 어댑터를 지연 생성)."""
    global _grounder
    if _grounder is None:
        with _lock:
            if _grounder is None:
                _grounder = KoreanLawGrounder()
    return _grounder


def set_parser(parser: Optional[Parser]) -> None:
    """Parser 구현을 주입한다(테스트/배포별 교체). None이면 다음 호출 시 기본 생성으로 복귀."""
    global _parser
    with _lock:
        _parser = parser


def set_grounder(grounder: Optional[Grounder]) -> None:
    """Grounder 구현을 주입한다(테스트/배포별 교체). None이면 다음 호출 시 기본 생성으로 복귀."""
    global _grounder
    with _lock:
        _grounder = grounder


def reset() -> None:
    """주입/캐시된 인스턴스를 모두 비운다(테스트 격리용)."""
    global _parser, _grounder
    with _lock:
        _parser = None
        _grounder = None
