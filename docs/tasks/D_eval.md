# 팀원 D — 평가 하니스 (`eval/`) + 골든셋

## 목표
LLM 없이 **검색·이탈 탐지 품질을 수치로 측정**한다. 특히 ablation(8.5)은 "RAG가 필요한가"를
주장이 아니라 **수치로 증명하는 대표 결과물**이므로 필수.

## 통과할 테스트 (순수 함수 — 의존성 0, 지금 바로 시작)
- [tests/eval/test_metrics.py](../../tests/eval/test_metrics.py)
- [tests/eval/test_run_eval.py](../../tests/eval/test_run_eval.py)
- [tests/eval/test_ablation.py](../../tests/eval/test_ablation.py)

## 구현 대상 (재사용 사슬: ablation → run_eval → metrics)
- [eval/metrics.py](../../eval/metrics.py) — `recall_at_k`, `reciprocal_rank`, `mrr`, `precision_recall`
- [eval/run_eval.py](../../eval/run_eval.py) — `evaluate(cases, k)` (metrics 재사용)
- [eval/ablation.py](../../eval/ablation.py) — `run_ablation(cases_by_variant, k)` (run_eval 재사용)
  - 변형 4종: `bm25` / `dense` / `hybrid` / `hybrid_rerank`

## 골든셋 (별도 산출물)
- 형태: (사용자 조항 ↔ 정답 표준조항 `clause_id`) + 이탈 라벨 (기획서 8.1)
- 함정 케이스 多: 말바꿈/순서 뒤바뀜/부분 누락 (8.3) — 검색이 틀리기 쉬운 케이스
- 저장 위치 제안: `eval/golden/` (JSON). 포맷은 PM과 합의.

## 완료 조건 (DoD)
- [ ] `tests/eval/` 3개 파일 전부 통과 (skip 제거 후)
- [ ] 골든셋 N건 작성 (함정 케이스 포함)
- [ ] ablation 표 출력: 변형 4종 × (recall@k, MRR) → BM25 대비 hybrid 우위가 수치로 보일 것
- [ ] **LLM-judge 사용 금지** — 결정론적 계산만 (AGENTS.md 규칙 #5)

## 참고
- 📖 **[eval/README.md](../../eval/README.md)** — 평가 철학·골든셋 포맷·지표별 사용법·MISSING 평가 (필독)
- 📝 **[golden 예시](../../eval/golden/sw_freelance.example.json)** — 함정 케이스 포함 7건 (현재 시드로 바로 실행 가능)
- 실제 검색 결과(cases) 수집은 B의 인덱스 + C의 검색이 필요 → 그 전까지 **순수 함수부터** 완성.
