"""동기 어댑터에서 async MCP 호출을 안전하게 실행하기 위한 브리지.

FastMCP streamable-http 서버는 동기 tool 함수를 **실행 중인 이벤트 루프 스레드**
위에서 호출한다. 그 안에서 `run_coroutine_threadsafe(coro, 현재_루프).result()`
처럼 현재 루프에 코루틴을 얹고 같은 스레드에서 블로킹하면, 코루틴이 영원히 실행되지
못해 **루프가 데드락**된다(서버 전체 동결 — parse_contract 한 번에 서버가 죽음).

이를 피하려고 실행 중인 루프가 감지되면 코루틴을 **별도 스레드의 새 이벤트 루프**에서
돌려 현재 루프를 건드리지 않는다. 현재 스레드는 결과를 기다리는 동안만 블로킹되며(직렬화),
루프 자체는 데드락되지 않는다.
"""

import asyncio
import concurrent.futures
from typing import Any, Coroutine


def run_coroutine_blocking(coro: Coroutine[Any, Any, Any]) -> Any:
    """코루틴을 동기적으로 실행하고 결과를 반환한다.

    - 실행 중인 이벤트 루프가 없으면(일반 동기 컨텍스트): `asyncio.run` 으로 직접 실행.
    - 이미 이벤트 루프 안이면(FastMCP 등): 별도 스레드의 새 루프에서 실행해
      현재 루프를 블로킹/재진입하지 않는다(데드락 방지).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 실행 중인 루프 없음 → 이 스레드에서 바로 실행
        return asyncio.run(coro)

    # 이미 루프 안 → 별도 스레드의 새 루프에서 실행 (현재 루프 미접촉)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
