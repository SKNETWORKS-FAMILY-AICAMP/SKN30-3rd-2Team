# 팀원 A — 표준조항 정규화 (`pipe/normalize`)

## 목표
변환된 마크다운(`data/02_converted/*.md`)을 **조항 단위로 분해하고 category 라벨을 붙여**
`data/03_normalized/*.json`(정답 데이터)을 만든다. 이게 전체 시스템의 **기준(정답)** 이다.

## 통과할 테스트
- [tests/pipe/test_normalize.py](../../tests/pipe/test_normalize.py)

## 구현 대상
- [src/pipe/normalize.py](../../src/pipe/normalize.py)
  - `split_markdown_clauses(md_text) -> list[Clause]` — `adapter.splitter` 로 청크를 나눈 뒤 `제N조` 헤더만 골라 `Clause` 로. (순수 분해는 splitter 가 이미 해줌 — 재구현 금지)
  - `label_category(num, title, text) -> Category` — 키워드 규칙으로 category 부여
  - `normalize_file(md_path, contract_type, version) -> list[StandardClause]` — 위 둘 조립 + `clause_id`·`source` 부여
- [src/pipe/2.normalize.py](../../src/pipe/2.normalize.py) — CLI: 02_converted 순회 → 03_normalized JSON 저장

## 입력 / 출력 계약
- 입력: `### 제N조(제목)` 헤더가 있는 마크다운
- 출력: `StandardClause` 규격 JSON ([data/README.md](../../data/README.md) 참고). enum 값은 `src/contracts/enums.py` 와 일치해야 적재됨.

## 완료 조건 (DoD)
- [x] `tests/pipe/test_normalize.py` 전부 통과 (skip 제거 후)
- [x] `data/03_normalized/standard_clauses.sw_freelance.json` 에 SW 도급계약서 전체 조항 정규화
- [x] `just migrate` 가 새 데이터로 에러 없이 적재됨
- [ ] (가능하면) 문화예술용역 계약서도 동일 절차로 추가

## 참고
- [src/pipe/README.md](../../src/pipe/README.md), [src/adapter/README.md](../../src/adapter/README.md) (splitter 사용법)
- category 후보: `enums.py` 의 `Category` (PAYMENT/IP_OWNERSHIP/...)

---

## 코드 리뷰 — `fd84e56` (feat(pipe): 표준조항 정규화 파이프라인 구현)

### 🔴 버그: `label_category` — `"하자보수"` 오탐 (RAG 치명적)

```python
# 현재 코드 (normalize.py:44~46)
if "보수" in search_text or "대금" in search_text or "임금" in search_text:
    return Category.PAYMENT
```

제19조 **하자의 담보** 본문에 "하자보수"가 포함되어 있어 `"보수"` 키워드에 매칭됨.
결과적으로 WARRANTY 조항이 PAYMENT로 분류됨.

category는 RAG 검색의 pre-filter로 사용되므로, 오분류된 조항은 검색 자체가 불가능해져
이탈 탐지가 완전히 실패함.

### 🔴 버그: fallback이 `SCOPE_SOW`

```python
# 현재 코드 (normalize.py:73)
return Category.SCOPE_SOW  # 매칭 없을 때 기본값
```

계약기간(제5조), 납품(제11조), 재하도급(제15조) 등 키워드 규칙이 없는 조항들이
전부 SCOPE_SOW로 잘못 분류됨. 버킷 오염.

### 🟡 스타일: 함수 내부 `import`

`normalize_file` 내부에 `import re`, `__main__` 블록에 `import os / json / Path`가
흩어져 있음. 파일 상단으로 이동할 것.

---

### 재구현 방향: 앵커 기반 임베딩 유사도 분류

`Category` enum이 다음과 같이 변경되었음:

- 각 멤버가 `(value, description, anchors)` 튜플 형태로 바뀌어 `cat.anchors`로 앵커 문장 목록에 접근 가능
- `DERIVATIVE_WORK` 제거 (IP_OWNERSHIP에 흡수) → 현재 코드의 `Category.DERIVATIVE_WORK` 참조는 `AttributeError`
- `CONTRACT_PERIOD`, `WARRANTY`, `DELIVERY_INSPECTION`, `SUBCONTRACTING` 신규 추가

이 `anchors`를 활용해 키워드 하드코딩을 임베딩 유사도 분류로 교체할 것.

```python
# 오프라인 준비 (build-db 시 또는 모듈 로드 시 1회)
import numpy as np
from adapter import embedder  # 기존 RAG 임베더 재사용

_category_vectors: dict[Category, np.ndarray] = {
    cat: np.mean(embedder.encode(cat.anchors), axis=0)
    for cat in Category
}

def label_category(num: str, title: str, text: str) -> Category:
    query_vec = embedder.encode(f"{title} {text[:200]}")
    scores = {
        cat: float(np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec)))
        for cat, vec in _category_vectors.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] < 0.45:
        raise ValueError(f"category 미분류 (유사도 부족): {num} {title}")
    return best
```

- 오탐 없음: `"하자보수"` → WARRANTY 앵커와 가장 유사
- 새 카테고리 추가 시 `enums.py`의 `anchors`만 수정하면 됨 (코드 변경 불필요)
- fallback 대신 예외 발생 → AGENTS.md "조용한 실패 금지" 준수
- 임베딩은 오프라인 정규화(`just build-db`)에서만 실행되므로 런타임 성능 무관

### 🟡 스타일: `__main__` 블록의 경로 하드코딩

```python
# 현재 코드
converted_dir = Path("data/02_converted")
normalized_dir = Path("data/03_normalized")
```

상대경로는 실행 위치에 따라 깨짐. `config.BASE_DIR` 를 사용할 것.

```python
from config import BASE_DIR

CONVERTED_DIR = BASE_DIR / "data" / "02_converted"
NORMALIZED_DIR = BASE_DIR / "data" / "03_normalized"
```


### 🟡 스타일: `__main__` 블록의 계약 유형 판별 if/elif

```python
# 현재 코드
if "기간제" in md_file.name or "근로" in md_file.name:
    contract_type = ContractType.SW_EMPLOYMENT
```

파일명 전체를 `dict` key로 선언해 if 분기를 제거할 것.
파일이 추가될 때 dict 한 줄만 수정하면 되고, 키워드 오탐도 없음.

```python
# 권장
FILENAME_CONTRACT: dict[str, ContractType] = {
    "201231_SW종사자_표준도급계약서.md":              ContractType.SW_FREELANCE,
    "201231_SW종사자_기간제,단시간__표준근로계약서.md": ContractType.SW_EMPLOYMENT,
}

contract_type = FILENAME_CONTRACT[md_file.name]  # 없으면 KeyError → 명시적 실패
```

