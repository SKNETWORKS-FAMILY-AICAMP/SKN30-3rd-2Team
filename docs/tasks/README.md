# 작업 분배 (Task Cards)

WorkShield 1차 MVP 모듈별 작업 카드입니다. 각자 본인 카드를 열어 시작하세요.

## 공통 작업 흐름 (TDD)
1. 내 카드의 **통과할 테스트 파일**을 먼저 읽는다 (= 무엇을 만들지가 거기 적혀 있음).
2. 그 파일 맨 위 `pytestmark = pytest.mark.skip(...)` **한 줄을 삭제**한다 → 빨강(실패) 확인.
3. 대상 모듈(스켈레톤 파일)의 `raise NotImplementedError` 를 **실제 구현으로 교체**한다.
4. `uv run pytest <내 테스트 경로>` 가 **초록(통과)** 이 될 때까지 반복한다.
5. 전체 `uv run pytest` 가 깨지지 않는지 확인하고 커밋/PR.

> 작업 전 [AGENTS.md](../../AGENTS.md) 와 본인 모듈 폴더의 `README.md` 를 반드시 읽으세요.
> 동결 계약(`src/contracts/`)·MCP 시그니처를 바꿔야 하면 **먼저 PM/리드와 합의**.

## 담당 & 의존성

| 담당 | 카드 | 모듈 | 선행(실제 데이터 통합 시) |
| --- | --- | --- | --- |
| 팀원 A | [A_normalize.md](A_normalize.md) | `pipe/normalize` + `03_normalized` 정답 데이터 | 02_converted (있음) |
| 팀원 B | [B_index.md](B_index.md) | `pipe/build_index` | A의 03_normalized |
| 팀원 C | [C_review_pipe.md](C_review_pipe.md) | `pipe/review_pipe` (review_contract) | B의 인덱스 |
| 팀원 D | [D_eval.md](D_eval.md) | `eval/metrics·run_eval·ablation` + 골든셋 | (집계는 독립) |
| 리드 | — | `mcp_server` + `demo` | C의 review_contract |

## 🚀 고도화 트랙 (코어 안정화 후 얹음)

> 기획서 7.1·7.2 / 10장 — **코어(A·B·C·D)가 도는 것을 확인한 뒤** 착수합니다. 포트폴리오 차별점이지만
> 동시 착수 시 코어 명제가 흐려지므로 **여유 팀원 또는 코어 완료자**가 맡습니다. enum·모델·DB·순수함수는 이미 준비됨.

| 카드 | 모듈 | 선행 | 난이도 |
| --- | --- | --- | --- |
| [E_toxic.md](E_toxic.md) | 독소조항 양방향 검색 (`toxic` 컬렉션 + 매칭) | B 인덱스 패턴 | 중 |
| [F_graph.md](F_graph.md) | 계약-조항 의존성 그래프 (`adapter/clause_graph`) | C review 흐름 | 상 |
| [G_sub_chunk.md](G_sub_chunk.md) | 거대 조항 서브청킹 + Max roll-up 검색 | B 인덱스 패턴 | 상 |
| [H_check_coverage.md](H_check_coverage.md) | 서브청크 커버리지 체크 (항 단위 삭제 탐지) | G roll-up | 상 |

> 두 고도화 모두 **순수함수(core)·데이터(seed)·모델은 완료**, 남은 것은 **인덱스/검색 결합 + review_contract 배선**입니다. 설계는 [src/pipe/README.md](../../src/pipe/README.md) §고도화 설계 참고.

## 중요: 대부분 "지금 바로" 병렬 착수 가능
테스트가 **fake 주입 / 순수 입력** 기반이라, 실제 인덱스·데이터 없이도 구현·통과가 가능합니다.
- A: 02_converted 마크다운만 있으면 시작 (있음)
- C: 테스트가 fake retriever/grounder 를 주입 → B의 실제 인덱스 없이 review_contract 구현 가능
- D: metrics·run_eval·ablation 순수 함수는 의존성 0 → 즉시 시작
- B: A의 03_normalized 가 있어야 실제 빌드가 의미 있음 (그 전엔 시드 3건으로 테스트 가능)

**실제 데이터 통합**(전체 코퍼스로 빌드→검색→평가)만 위 선행 순서를 따릅니다.

## 진행 현황 보드 (skip 개수 = 남은 작업)
```
uv run pytest -ra        # skip 목록으로 남은 규격 확인
uv run pytest -q         # 전체 통과/스킵 요약
```
