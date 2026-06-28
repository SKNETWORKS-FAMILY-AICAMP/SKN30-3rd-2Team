# src/core/ — 이탈 탐지 알고리즘 (순수 함수 · TDD 대상)

WorkShield의 **핵심 기여**(기획서 7장). "표준 대비 이탈을 탐지"하는 로직이 여기 모입니다.

> 원칙: **순수 함수.** I/O 없음(DB·네트워크·파일 접근 금지), 부수효과 없음. 같은 입력 → 항상 같은 출력. 그래서 **테스트로 규격을 고정**하기 가장 좋은 곳입니다 → 팀원은 미리 작성된 테스트를 통과시키면 끝.

DB 조회·임베딩 같은 외부 작업이 필요하면 **인자로 받습니다**(adapter를 직접 import 하지 않음). 조립은 `pipe/`가 담당합니다.

## 함수 (모두 `from core import ...`)

| 함수 | 역할 | 기획서 |
| --- | --- | --- |
| `select_best_match(candidates, threshold)` | 후보 중 최고 점수 선택, 임계치 미만이면 매칭 없음 처리 | 7-②③ |
| `classify_clause_deviation(user_text, matched_standard, score, match_threshold, change_threshold)` | `MISSING`/`EXTRA`/`CHANGED`/`NONE` 분류 | 7-③ |
| `calculate_text_similarity(t1, t2)` | 두 본문 일치율(0~1) | 7-③ |
| `detect_missing_clauses(all_standard, matched_ids)` | 한 번도 매칭 안 된 표준조항 = 누락 | 3.2 MISSING |
| `traverse_related_risks(adjacency_list, deviated_id, max_depth)` | 의존성 그래프 DFS — 함께 검토할 조항 | 7.1 (고도화 A) |
| `detect_toxic_patterns(matches, threshold)` | 독소 패턴 매칭 임계 필터 | 7.2 (고도화 B) |

## 규칙
- adapter·config import 금지. 외부 데이터는 **인자로 주입**.
- 출력은 `contracts` 모델/enum으로. 빈 결과도 `NO_MATCH` 등 명시 표식.
- **1차에는 LLM·해석 생성 금지.** 검색·비교·분류·규칙만. (AGENTS.md 규칙 #1)
- 새 로직은 `tests/core/`에 테스트부터 작성(또는 통과)하고 구현.
