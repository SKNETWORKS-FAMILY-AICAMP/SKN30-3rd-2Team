# src/core/ — 이탈 탐지 알고리즘 (순수 함수 · TDD 대상)

WorkShield의 **핵심 기여**(기획서 7장). "표준 대비 이탈을 탐지"하는 로직이 여기 모입니다.

> 원칙: **순수 함수.** I/O 없음(DB·네트워크·파일 접근 금지), 부수효과 없음. 같은 입력 → 항상 같은 출력. 그래서 **테스트로 규격을 고정**하기 가장 좋은 곳입니다 → 팀원은 미리 작성된 테스트를 통과시키면 끝.

DB 조회·임베딩 같은 외부 작업이 필요하면 **인자로 받습니다**(adapter를 직접 import 하지 않음). 조립은 `pipe/`가 담당합니다.

---

## 파이프라인 속 위치

```
[retriever] top-k 후보 반환
      ↓
select_best_match()          ← 리랭커 점수 기준 최고 후보 선택 + 임계치 게이트
      ↓
[pipe] 후보 0개이면 NO_MATCH 직접 처리  ← core가 아닌 pipe 책임
      ↓
classify_clause_deviation()  ← EXTRA / CHANGED / NONE 확정
      ↓
detect_missing_clauses()     ← 루프 종료 후 한 번, MISSING 확정
      ↓
traverse_related_risks()     ← CHANGED·MISSING 확정 조항에 대해 연관 조항 추적 (고도화 A)
detect_toxic_patterns()      ← 동일 조항에 대해 독소 패턴 역방향 검색 (고도화 B)
```

---

## 함수 (모두 `from core import ...`)

| 함수 | 파이프라인 단계 | 반환 |
| --- | --- | --- |
| `select_best_match(candidates, threshold)` | 리랭커 직후 — 최고 후보 선택 | `(StandardClause \| None, float)` |
| `calculate_text_similarity(t1, t2)` | classify 내부 — **항↔항 정렬** 후 본문 변경량 측정 | `float` 0~1 |
| `detect_critical_changes(user_text, standard_text)` | classify 내부 — 부정어 플립·숫자·당사자 스왑 검출 (NONE 차단 게이트) | `List[str]` 사유 |
| `classify_clause_deviation(user_text, matched_standard, score, match_threshold, change_threshold)` | 조항 단위 루프 — EXTRA / CHANGED / NONE 판정 | `Deviation` |
| `detect_missing_clauses(all_standard, matched_ids)` | 루프 종료 후 1회 — 한 번도 매칭 안 된 표준조항 수집 | `List[StandardClause]` |
| `traverse_related_risks(adjacency_list, deviated_id, max_depth)` | 이탈 확정 후 — 연관 위험 조항 DFS 탐색 (고도화 A) | `List[str]` clause_id |
| `detect_toxic_patterns(matches, threshold)` | 조항 단위 루프 — 독소 패턴 역방향 검색 필터 (고도화 B) | `List[ToxicPattern]` |

---

## Deviation 분류 체계와 함수 대응

각 Deviation 값이 어느 함수에서 결정되는지, 주어가 무엇인지 정리합니다.

| Deviation | 주어 | 결정 위치 | 의미 |
| --- | --- | --- | --- |
| `EXTRA` | 사용자 조항 | `classify_clause_deviation` | 대응 표준조항 없거나 유사도 미달 — 비표준 추가 조항 |
| `CHANGED` | 사용자 조항 | `classify_clause_deviation` | 표준조항과 매칭됐지만 본문 내용이 크게 다름 |
| `NONE` | 사용자 조항 | `classify_clause_deviation` | 표준조항과 매칭되고 본문도 일치 — 이탈 없음 |
| `MISSING` | **표준조항** | `detect_missing_clauses` | 표준에는 있는데 사용자 계약서에 대응 조항이 없음 |
| `NO_MATCH` | — | **pipe 레이어** | 검색 자체가 후보를 반환하지 못함 (core 밖) |

> `MISSING`의 주어가 사용자 조항이 아니라 표준조항이기 때문에, 단일 조항 루프 안에서 판단할 수 없어 `detect_missing_clauses`로 분리됩니다.
>
> `NO_MATCH`는 검색 인프라 문제이므로 core가 아닌 pipe에서 직접 처리합니다. `classify_clause_deviation`에 후보 없음(`matched_standard=None`)이 들어오는 경우는 "후보는 있었으나 전부 threshold 미달"인 경우만이므로 `EXTRA`가 올바릅니다.

---

## 임계치(Threshold) 가이드

두 임계치는 역할이 다르며, 초기값은 eval 결과로 조정합니다.

| 파라미터 | 기본값 | 역할 |
| --- | --- | --- |
| `match_threshold` | 0.5 (pipe 주입) | 대응 표준조항이 '존재한다'고 볼 수 있는 최소 리랭커 점수. 미달 → `EXTRA` |
| `change_threshold` | 0.85 | 매칭된 조항의 본문이 '충분히 같다'고 볼 수 있는 **항↔항 정렬** 일치율. 미달 → `CHANGED` |

`change_threshold`에 임베딩 유사도 대신 SequenceMatcher를 쓰는 이유: 법률 문서에서는 미묘한 문구 변경이 법적으로 큰 차이를 만듭니다. 의미 벡터상 가까운 두 조항도 내용 변경으로 보아야 할 수 있으므로, 글자 단위 비교가 더 적합합니다.

**비교 단위는 조↔조가 아니라 항↔항입니다** (v1 리뷰 §2 원인 A 수정). 사용자 조항(단문)을 표준 '조 전체'와 통째로 비교하면 `ratio`의 상한이 길이 비로 묶여 내용이 같아도 NONE에 도달할 수 없습니다(v1 축퇴). 그래서 양쪽을 `split_into_sub_chunks`로 항·호 단위로 쪼개 최적 쌍을 정렬한 뒤, 헤더(`제N조(제목)`)·항 기호(`①` vs `1.`)·공백을 제거한 문장↔문장 일치율의 길이 가중 평균을 씁니다.

**NONE 의 정의는 엄격안**입니다: 서식(헤더·기호·공백)만 다르면 NONE, 문구가 바뀌면(말바꿈 포함) CHANGED. 또한 일치율이 임계값을 넘어도 `detect_critical_changes`가 부정어 플립("부과한다"↔"부과하지 아니한다")·숫자 변경("10%"↔"50%")·당사자 스왑("갑"↔"을")을 잡으면 CHANGED로 강제합니다 — 글자 몇 자 차이가 법적으로 정반대가 되는 케이스를 임계값과 독립적으로 방어합니다.

---

## 규칙
- adapter·config import 금지. 외부 데이터는 **인자로 주입**.
- 출력은 `contracts` 모델/enum으로. 빈 결과도 `NO_MATCH` 등 명시 표식.
- **1차에는 LLM·해석 생성 금지.** 검색·비교·분류·규칙만. (AGENTS.md 규칙 #1)
- 새 로직은 `tests/core/`에 테스트부터 작성(또는 통과)하고 구현.
