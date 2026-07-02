# v1 · Track B (실계약) — M:N 커버리지 평가

> 자동 생성: `eval.run_eval.evaluate_coverage_b` · 2026-07-02 11:32:25 · `APP_ENV=prod` · 문서 5건 × 유형 3종
> ⚠️ 라벨 없는 자동 지표 — **절대값은 정답이 아니라 vN(=시스템 버전) 비교 신호**다. 유형 간 조항 겹침으로 커버리지가 비슷할 수 있으니 델타(vN 간)로 해석하고 최적화 목표로 삼지 말 것.
> `coverage = (전체 표준 − MISSING) / 전체 표준`. best-fit = 커버리지 최대 유형.

## 커버리지 매트릭스 (문서 × 유형 — 셀: `coverage (NM=NO_MATCH)`)

| 문서 | 조항수 | SW_FREELANCE | SI_SUBCONTRACT | SM_SUBCONTRACT | best-fit |
| --- | --- | --- | --- | --- | --- |
| raw/test_sunny10.pdf | 14 | 0.52 (NM=0) | 0.11 (NM=0) | 0.11 (NM=0) | SW_FREELANCE |
| raw/동행용역계약서_김효선.pdf | 15 | 0.52 (NM=0) | 0.10 (NM=0) | 0.11 (NM=0) | SW_FREELANCE |
| raw/프리랜서_고용계약서_샘플_문서킹.docx | 12 | 0.43 (NM=0) | 0.08 (NM=0) | 0.07 (NM=0) | SW_FREELANCE |
| raw/프리랜서_고용계약서_샘플_자비스.docx | 10 | 0.35 (NM=0) | 0.07 (NM=0) | 0.06 (NM=0) | SW_FREELANCE |
| raw/프리랜서_고용계약서_샘플_프리폼.docx | 14 | 0.52 (NM=0) | 0.10 (NM=0) | 0.09 (NM=0) | SW_FREELANCE |

## 문서별 상세 (best-fit 유형 기준 deviation 분포)

- **raw/test_sunny10.pdf** (best-fit `SW_FREELANCE`): 조항 14 · coverage 0.52 (표준 12/23) · NO_MATCH 0 · 분포 {'CHANGED': 14}
- **raw/동행용역계약서_김효선.pdf** (best-fit `SW_FREELANCE`): 조항 15 · coverage 0.52 (표준 12/23) · NO_MATCH 0 · 분포 {'CHANGED': 15}
- **raw/프리랜서_고용계약서_샘플_문서킹.docx** (best-fit `SW_FREELANCE`): 조항 12 · coverage 0.43 (표준 10/23) · NO_MATCH 0 · 분포 {'CHANGED': 12}
- **raw/프리랜서_고용계약서_샘플_자비스.docx** (best-fit `SW_FREELANCE`): 조항 10 · coverage 0.35 (표준 8/23) · NO_MATCH 0 · 분포 {'CHANGED': 10}
- **raw/프리랜서_고용계약서_샘플_프리폼.docx** (best-fit `SW_FREELANCE`): 조항 14 · coverage 0.52 (표준 12/23) · NO_MATCH 0 · 분포 {'CHANGED': 14}

## 강건성 스팟체크 (사람 작성 — 정성, 지표 없음)

> AI 리뷰어 초안(객관 관찰) — 사람이 이어서 확인. 분석·다음 버전 반영점은 [v1_b_review.md](v1_b_review.md).

- 파싱 성공/실패 · 깨진 조항 여부 — **5/5 성공**(파서 `제N조` 라인경계 분해 수정 후 10~15조). 직전 실행은 0건 축퇴였음. 깨진 조항 없음.
- best-fit 이 상식과 맞는가 · 유형 간 분리가 뚜렷한가 — **5/5 SW_FREELANCE**(프리랜서/용역 상식 부합), SW 커버리지가 SI/SM 의 **~5배**로 분리 뚜렷. 단 test_sunny10·동행용역이 실제 SW 계약인지 원문 확인 권장.
- NO_MATCH 폭주·비정상 deviation 분포 여부 — NO_MATCH **0**(정상). ⚠️ **deviation 전부 CHANGED**(NONE=0) — 분류기 축퇴(Track A 원인 A 재현), 파싱·검색 문제 아님. 상세 [v1_b_review.md](v1_b_review.md) §3.
- 기타 — 표본 5건 전부 SW 도메인이라 SI/SM 판별력은 미검증(양방향 검증 필요).
