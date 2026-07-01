# 팀원 B — 인덱스 빌드 (`pipe/build_index`)

## 목표
SQLite 의 표준조항을 **bge-m3 로 임베딩해 Chroma 인덱스로 적재**한다. 이걸로 하이브리드
검색이 가능해진다. (형상관리상 Chroma 는 재생성 파생물 — git 에 안 올림)

## 통과할 테스트
- [tests/pipe/test_build_index.py](../../tests/pipe/test_build_index.py) (통합·느림 — 모델 로딩/DB 필요)

## 구현 대상
- [src/pipe/build_index.py](../../src/pipe/build_index.py)
  - `build_standard_index(collection_name="standard_clauses") -> int`
    1. `from adapter import db, vector`
    2. `db.fetch_all("SELECT clause_id, text, contract_type, category, title FROM standard_clauses")`
    3. `vector.add_documents(collection_name, documents=[text...], ids=[clause_id...], metadatas=[{contract_type, category, ...}])`
    4. 적재 건수 반환
- [src/pipe/3.build_index.py](../../src/pipe/3.build_index.py) — CLI (이미 build_standard_index 호출하도록 연결됨)

## 입력 / 출력 계약
- 입력: `standard_clauses` 테이블 (먼저 `just migrate` 실행)
- 출력: Chroma `standard_clauses` 컬렉션. **메타데이터에 `contract_type`·`category`·`clause_id` 필수** (검색 시 필터·식별).
- 검증: `vector.search("standard_clauses", "저작권의 귀속", search_type="hybrid")` 결과에 `sw_freelance-art20` 포함.

## 완료 조건 (DoD)
- [x] `just migrate && uv run pytest tests/pipe/test_build_index.py` 통과
- [x] `just build-db` 가 끝까지(migrate → build-index) 에러 없이 동작
- [x] 적재 건수 로그 출력

## 참고
- [src/adapter/README.md](../../src/adapter/README.md) (`vector.add_documents`, `vector.search`)
- 임베딩은 `adapter.vector` 가 내부에서 자동 수행 (직접 embedder 호출 불필요)

---

## 리뷰 피드백 (구현 전 반드시 확인)

### [필수] SQLite가 비어있을 때 기존 인덱스가 조용히 삭제됨

현재 코드는 재빌드 시 기존 Chroma 문서를 먼저 지운 뒤 SQLite를 읽는 순서로 동작한다.
`just migrate` 없이 실행하거나 테이블이 비어있으면, **삭제는 실행됐는데 적재는 일어나지 않아**
Chroma 인덱스가 빈 상태가 된다. `vector.add_documents`는 빈 리스트를 받으면 내부에서 조용히 return하기 때문에 예외도 발생하지 않는다.

AGENTS.md 규칙: "조용한 실패 금지 — 빈 값 대신 명시 표식·예외"

```python
rows = db.fetch_all("SELECT ...")
if not rows:
    raise RuntimeError("standard_clauses 테이블이 비어 있습니다. 먼저 `just migrate`를 실행하세요.")
```

---

### [필수] delete → add가 원자적이지 않아 임베딩 실패 시 이전 인덱스 복구 불가

기존 문서를 먼저 지우고 나서 임베딩·적재를 시도하는 구조이기 때문에,
임베딩 도중 예외(OOM, 모델 미로드 등)가 발생하면 이전에 잘 동작하던 인덱스가 비어버린다.

delete를 add 성공 **이후**로 옮기거나, 실패 시 예외 메시지에 상태를 명시해 운영자가 인지할 수 있도록 한다.

```python
# 권장 순서: 새 문서를 먼저 upsert하고, 구 문서를 나중에 정리
# (혹은 try/except 로 감싸 실패 시 "인덱스가 비어있을 수 있음" 경고 로그 출력)
try:
    vector.add_documents(...)
except Exception as e:
    raise RuntimeError(f"Chroma 적재 실패 — 인덱스가 비어있을 수 있습니다: {e}") from e
# add 성공 후 delete
```

---

### [권장] ID 조회 시 문서 전체를 메모리에 로드하지 말 것

재빌드 전 기존 ID 목록을 얻을 때 `.get()`을 인자 없이 호출하면 문서 텍스트·메타데이터 전체가 메모리에 올라온다.
`include=[]`를 전달하면 ID만 반환되어 불필요한 메모리 사용을 피할 수 있다.

```python
# 변경 전
existing = vector.get_collection(collection_name).get()

# 변경 후
existing = vector.get_collection(collection_name).get(include=[])
```
