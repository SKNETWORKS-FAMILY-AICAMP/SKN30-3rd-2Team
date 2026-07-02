# data/ — 데이터 & 형상관리 정책

WorkShield 의 모든 데이터가 모이는 곳입니다. **"무엇을 git 으로 관리하고, 무엇을 재생성하는가"** 의 규칙을 여기서 정의합니다. (기획서 5.5)

## 핵심 원칙: 정답은 git, 인덱스는 재생성

> **정답의 원천(source of truth) = 정규화된 조항 데이터(normalize JSON) + 스키마(SQL)**.
> SQLite·Chroma 인덱스는 거기서 **다시 생성 가능한 파생물**이므로 git 으로 관리하지 않습니다.

이유:
- 바이너리 인덱스를 커밋하면 **머지 충돌·용량 증가**가 생기고 **diff 리뷰가 불가능**합니다.
- 반대로 normalize JSON 은 사람이 읽을 수 있어, PR 에서 *"이 조항의 category 라벨이 바뀌었다"* 가 깔끔하게 보입니다.
- 코퍼스가 작아 **재생성이 빠릅니다**.

## 폴더 구조

| 경로 | 내용 | git |
| --- | --- | --- |
| `01_raw/` | 원본 표준계약서 (HWP 6종) | ✅ 커밋 |
| `02_converted/` | kordoc 으로 변환한 마크다운. 오프라인 1회 변환 + 수동 정제 체크포인트 | ✅ 커밋 |
| `02_converted/hold/` | 본계약에서 분리한 **부속 계약서**(비밀유지·약식변경·직접지급합의·연동계약) — 1차 범위에서 보류 | ✅ 커밋 |
| `02_converted/images/` | 변환 과정에서 추출된 이미지 | ✅ 커밋 |
| `03_normalized/` | **정규화된 조항(정답).** `StandardClause` / `StandardSubChunk` / `ClauseRelation` / `ToxicPatternRecord` 스키마를 따르는 JSON | ✅ 커밋 |
| `toxic/` | 독소조항 큐레이션 참고자료 (프리랜서 가이드라인 PDF·불공정계약유형 md) | ✅ 커밋 |
| `migration/01.CREATE_TABLE.sql` | DB 스키마(DDL) | ✅ 커밋 |
| `migration/contract.sqlite3` | **생성물.** normalize 에서 빌드된 SQLite | ❌ gitignore |
| `migration/chroma.sqlite3`, `migration/<uuid>/` | **생성물.** Chroma 벡터 인덱스 | ❌ gitignore |
| `99_uploads/` | 사용자 업로드 임시 파일 | ❌ gitignore |

## normalize JSON 규격

각 파일은 해당 pydantic 모델([src/contracts/models.py](../src/contracts/models.py))의 배열입니다. 적재 시 검증되며, enum 에 없는 값이 있으면 **즉시 실패**합니다.

| 파일 | 모델 | 담당 |
| --- | --- | --- |
| `standard_clauses.<contract_type>.<version>.json` | `StandardClause[]` | 표준조항 정규화 담당 |
| `standard_sub_chunks.<contract_type>.<version>.json` | `StandardSubChunk[]` | 표준조항 정규화 담당 |
| `clause_relations.json` | `ClauseRelation[]` (고도화 A) | 도메인 큐레이션 |
| `toxic_patterns.json` | `ToxicPatternRecord[]` (고도화 B) | 도메인 큐레이션 |

현재 커버하는 계약 종류·버전: `si_subcontract`(2022·2025) · `sm_subcontract`(2022·2025) · `sw_employment`(2020) · `sw_freelance`(2020).

> 새 계약 종류를 추가할 때는 **코드를 고치지 않고** `standard_clauses.<new_type>.<version>.json` 파일과 `ContractType` enum 값 하나만 추가하면 됩니다. (기획서 3.3 확장성)

## 재생성 방법

```bash
just build-db      # 스키마 적용 → normalize 적재(SQLite) → 임베딩 → Chroma 인덱스
# 또는 단계별로:
just migrate       # SQL 스키마 + normalize JSON → SQLite 까지만
just build-index   # SQLite → bge-m3 임베딩 → Chroma 인덱스
```

clone 후 위 명령 한 번이면 누구나 **동일한 DB** 를 얻습니다. 바이너리를 주고받지 않습니다.
