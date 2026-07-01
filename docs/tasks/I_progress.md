# 고도화 — `review_contract` 진행률(progress) 알림

> MCP 고도화 6제안 중 **5번**. 나머지(1·2·3·4·6)는 완료. 이 카드만 **동결 계약 변경**이 걸려
> 보류 상태다. **착수 전 아래 §승인 게이트 3건을 PM/리드가 확정**해야 코딩을 시작한다.

## 목표
조항이 많은 계약서에서 `review_contract`가 오래 걸릴 때, MCP progress notification으로
클라이언트가 "N/전체 조항 처리 중"을 실시간 표시하게 한다. 특히 2차 웹앱 UX에 직결.

## ⛔ 이 카드가 보류인 이유 — 핵심 발견
FastMCP는 **동기 도구(`def`)를 이벤트 루프에서 그대로 실행**한다
([func_metadata.call_fn_with_arg_validation](../../.venv) — `to_thread` 없이 `return fn(...)`).
현재 [review_contract](../../src/server/server.py)는 동기이고 그 안에서
[review_contract_pipe](../../src/pipe/review_pipe.py)를 통째로 호출한다.

→ 동기 콜백을 넣어도 **파이프 실행 내내 이벤트 루프가 블록**되어 `report_progress`(async)가
전송될 틈이 없다. 즉 progress는 "콜백 하나 추가" 수준이 아니라 **실행 모델 변경**이다:
`review_contract`를 `async def`로 바꾸고 파이프를 워커 스레드에서 돌려야 한다.

- `Context.report_progress(progress, total, message)`는 async. 클라이언트가 `progressToken`을
  안 보내면 **자동 no-op** → progress 미지원 클라이언트에 안전(하위호환).
- 브릿지: `anyio.to_thread.run_sync(pipe...)`로 파이프를 스레드 실행 +
  스레드 안에서 `anyio.from_thread.run(ctx.report_progress, i, n)`로 루프에 콜백.
  anyio 4.14.1에 두 프리미티브 모두 존재함을 확인.

## Granularity 현실 점검 (어디에 tick이 의미 있나)
[review_contract_pipe](../../src/pipe/review_pipe.py) 흐름:
1. **배치 검색**(`search_many` ×3 컬렉션) — 하나의 불투명 블록. 임베딩 왕복 대부분 여기. tick 못 쪼갬.
2. **조항별 루프** — 조항마다 rerank ×3 + coverage + grounding(CHANGED시 외부 law MCP).
   **유일하게 조항 단위 tick이 의미 있는 구간.**
3. **MISSING 루프** — 누락 표준마다 grounding.

정직한 결론: 부드러운 "N/전체" progress는 2단계 루프에만 존재. 1단계 배치 검색 동안은
"검토 준비 중"에서 멈춰 보인다. **이득은 조항 수(루프 비중)에 비례.**

## 설계 옵션

| | A. 콜백 주입 (권장) | B. 페이즈 progress | C. 웹앱 스트리밍 |
| --- | --- | --- | --- |
| 방식 | 파이프에 `progress_callback` 추가, 루프 안에서 조항마다 호출 | 서버에서 파싱/로드/실행/완료 경계에만 tick | MCP progress 대신 2차 웹앱이 조항 루프를 SSE로 스트리밍 |
| tick | 조항 수만큼(진짜 N/전체) | 3~4개(거침) | 조항 수만큼 |
| 동결 계약 | **파이프 시그니처 변경 → rule 2 합의** | 없음(서버만) | 없음(파이프 불변) |
| 대상 소비자 | 범용 MCP 클라이언트 포함 | 범용 포함 | 우리 웹앱 전용 |
| UX | 실제 진행률 | 긴 정지(이득 작음) | 실제 진행률 |

- **범용 MCP 클라이언트까지 지원**이 목표면 → **A**.
- **소비자가 우리 웹앱뿐**이면 → **C**가 동결 계약을 안 건드려 ROI 우위.

## 구현 대상 (A안 채택 + 승인 후)
1. **[src/pipe/review_pipe.py](../../src/pipe/review_pipe.py)** — 시그니처에
   `progress_callback: Optional[Callable[[int, int], None]] = None` (keyword-only, 기본 None).
   2단계 루프 끝에서 `if progress_callback: progress_callback(done, total)` 호출.
   순수성 유지: 콜백은 부수효과만, 반환값 없음. **None이면 기존 동작 완전 불변**(하위호환).
2. **[src/server/server.py](../../src/server/server.py) `review_contract`** — `async def`로 전환 +
   `ctx: Context` 파라미터 추가. 파이프 호출을 `anyio.to_thread.run_sync`로 감싸고,
   동기 콜백이 `anyio.from_thread.run(ctx.report_progress, done, total, msg)`로 브릿지.
   배치 검색 전/후 페이즈 tick 1~2개도 추가(1단계 정지 완화).
3. 파일 IO(`_resolve_contract_file`)·`_load_standards`는 async 본문에서 먼저 처리하고,
   순수 CPU/IO-bound 파이프 본체만 스레드로 넘긴다.
4. `classify_clause`·`match_clause` 등 단발 도구는 progress 불필요 → 그대로 둔다.

## 통과할 테스트 (TDD)
- 파이프: `progress_callback`이 조항 수만큼 순서대로(1..N) 호출되는지 단위 테스트 1건 추가.
  `None`일 때 동작 불변(기존 [tests/pipe/test_review_pipe.py](../../tests/pipe/test_review_pipe.py) 15건이 커버).
- 서버: `progressToken` 없는 호출에서 no-op으로 정상 결과 반환(회귀 방지).
  progress 전송은 FakeContext로 `report_progress` 호출 인자 검증.

## 리스크 (착수 전 검증)
- **async 전환 부작용**: `db`는 thread-local sqlite(안전). 단 **law MCP 어댑터
  ([korean_law_mcp](../../src/adapter/korean_law_mcp.py))가 자체 이벤트 루프를 쓰는지** 확인 —
  워커 스레드 안 중첩 루프 충돌 가능. **최우선 검증 항목.**
- 파이프 시그니처 변경은 하위호환이어도 동결 대상 → §승인 게이트 통과 전 코딩 금지.

## 완료 조건 (DoD)
- [ ] §승인 게이트 3건 확정
- [ ] `progress_callback=None` 회귀: 기존 파이프 테스트 15건 그대로 통과
- [ ] `progressToken` 미지원 클라이언트에서 `review_contract` 정상 결과 반환
- [ ] `progressToken` 지원 시 조항별 progress notification 수신 확인
- [ ] law MCP 어댑터 중첩 루프 충돌 없음 검증

## ⚠ 승인 게이트 (진행 전 확정 필요)
1. 파이프 시그니처에 `progress_callback` 추가 승인 (AGENTS.md rule 2)
2. **progress 소비자: 범용 MCP 클라이언트까지인가, 우리 웹앱뿐인가** → A vs C 결정
3. `review_contract`의 `async def` 전환 승인 (실행 모델 변경)

## 참고
- [src/server/README.md](../../src/server/README.md) §7 절대 규칙 (LLM 없음·빈 응답 금지는 무관, 실행 모델만)
- [src/pipe/README.md](../../src/pipe/README.md), 기획서 4장(MCP 동결 계약)
