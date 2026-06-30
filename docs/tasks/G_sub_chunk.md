# [고도화 G] 거대 조항 서브청킹 및 Parent Roll-up 검색

**거대 조항(제58조 등)의 임베딩 희석 문제를 해결하기 위해, 인덱싱은 자식(항) 단위로 수행하고 결과는 부모(조) 단위로 취합하여 검색 해상도와 삭제 탐지율을 높이는 검색 고도화 설계**

---

## 1. 배경 및 목적

*   **기존 미시 원소 비교(구 Z_Lever)의 한계 및 철회:**
    *   조항 내부의 문장 단위(Element)를 일일이 정렬하고 룰 기반 법률 레버(양태, 당사자, 수치 등)를 비교하려던 기존 설계는 지나치게 복잡하고 취약(Fragile)한 오버엔지니어링으로 판정됨.
    *   "어디가 어떻게 불리한가"의 해석은 본질적으로 2차 트랙(LLM 영역)의 역할이며, 1차 MVP는 **"어느 조항이 CHANGED(변경)되었는지"를 정량적/결정론적으로 정확히 탐지**하는 역할로 제한함.
    *   이에 따라 동결 계약(enums, models) 변경 승인 안건은 전면 철회함.
*   **임베딩 희석(Embedding Dilution) 문제:**
    *   제58조와 같이 1,500자가 넘고 10여 개의 항으로 구성된 거대 조항을 통째로 하나의 벡터로 임베딩하면, 특정 항(예: ⑩ 지연이자 지급 의무) 하나가 통째로 삭제되어도 전체 유사도 점수 평균화에 묻혀 `NONE`(이탈 없음)으로 통과해 버리는 오탐 리스크가 존재함.
    *   임계값(`change_threshold`)을 높이는 방법은 이 시나리오(9/10 항 일치)에서 임계값을 0.99로 올려도 통과하므로 주 대응책이 될 수 없음.
*   **해결 전략:**
    *   저장·반환·2차 전달 단위는 **조 전체(통짜, 항·호 구조 보존)**로 유지.
    *   검색 단계에서는 **서브청크 + Max 롤업**으로 올바른 부모 조항을 찾고, 찾은 후에는 **커버리지 체크**로 삭제된 항을 탐지한다. 두 역할은 분리된다.

---

## 2. 세부 아키텍처 및 구현 설계

### 0단계: 스키마 및 모델 신설 (가법·하위호환)

> 기존 `standard_clauses` 테이블·`StandardClause` 모델·`DeviationResult`·MCP 시그니처는 **무변경**. 아래는 순수 신설(additive)이다.

*   **SQLite — `standard_sub_chunks` 테이블 추가** ([01.CREATE_TABLE.sql](../../data/migration/01.CREATE_TABLE.sql)):
    ```sql
    CREATE TABLE IF NOT EXISTS standard_sub_chunks (
        sub_chunk_id     TEXT PRIMARY KEY,  -- 예: sw_freelance-art58-sub01
        parent_clause_id TEXT NOT NULL,     -- FK → standard_clauses.clause_id
        sub_chunk_index  INTEGER NOT NULL,  -- 항 순서 (0-based)
        text             TEXT NOT NULL,
        FOREIGN KEY (parent_clause_id) REFERENCES standard_clauses(clause_id)
    );
    CREATE INDEX IF NOT EXISTS idx_sub_parent ON standard_sub_chunks(parent_clause_id);
    ```
    커버리지 체크 시 `SELECT * FROM standard_sub_chunks WHERE parent_clause_id = ?`로 표준 서브청크 전체 목록을 열거하기 위해 SQLite에도 저장한다. Chroma의 WHERE 필터는 벡터 검색에 최적화되어 있어 전체 목록 열거에 부적합하다.

*   **Pydantic — `StandardSubChunk` 모델 추가** ([models.py](../../src/contracts/models.py)):
    ```python
    class StandardSubChunk(BaseModel):
        """거대 조항의 항·호 단위 서브청크 (coverage 체크 및 Chroma 인덱싱용)"""
        sub_chunk_id: str       # sw_freelance-art58-sub01
        parent_clause_id: str   # sw_freelance-art58
        sub_chunk_index: int    # 항 순서 (0-based)
        text: str
    ```

*   **Chroma — `standard_sub_chunks` 컬렉션 신설**: 기존 `standard_clauses` 컬렉션은 유지하고 별도 컬렉션 추가. 메타데이터에 `parent_clause_id` 저장.

### 1단계: 조건부 서브청크 인덱스 구축 (오프라인/인덱스 빌드)

*   **분할 조건 (초기값 — 코퍼스 측정 후 조정):**
    *   텍스트 길이 **500자 초과** OR 항·호 기호(①②, 1. 2. 등) **3개 이상**이면 거대 조항으로 판정하여 항 단위 서브청크로 분할.
    *   조건 미달 조항은 조 전체를 1청크로 유지.
*   **메타데이터 바인딩:** ChromaDB 적재 시 `parent_clause_id`·`sub_chunk_index` 저장.
    ```json
    {
      "id": "sw_freelance-art58-sub01",
      "text": "① 원사업자는 수급사업자에게 대금을 ... 지급하여야 한다.",
      "metadata": {
        "parent_clause_id": "sw_freelance-art58",
        "sub_chunk_index": 0
      }
    }
    ```
*   **코드 파일:** [build_index.py](../../src/pipe/build_index.py) — 조건부 청킹 로직 + SQLite `standard_sub_chunks` 적재 + Chroma 컬렉션 빌드.

### 2단계: Max Roll-up 검색 (런타임 — 부모 조항 확보)

*   **목적:** 사용자 조항에 가장 잘 대응하는 표준 부모 조항을 찾는다. (삭제 탐지는 3단계)
*   **메커니즘:**
    1.  사용자 조항을 쿼리로 `standard_sub_chunks` Chroma 컬렉션에서 Top-K 서브청크 탐색.
    2.  `parent_clause_id` 기준으로 그룹화(Group by).
    3.  각 부모 후보에 대해 **Max Score**(하나라도 잘 맞으면 후보 부모로 올림)로 집계 → 최고 점수 부모를 매칭 대상으로 확정.
    *   Mean이 아닌 Max를 쓰는 이유: 거대 조항에서 사용자가 특정 항만 언급할 경우 Mean이면 묻히기 때문.
*   **코드 파일:** [vector_manager.py](../../src/adapter/vector_manager.py) — `search` 구현부에 롤업 집계 로직 추가.

### 3단계: 커버리지 체크 (런타임 — 삭제 탐지의 주 메커니즘)

*   **목적:** 매칭된 부모 조항의 표준 서브청크 중 사용자 서브청크에 대응하는 것이 없는 항을 탐지한다.
*   **메커니즘:**
    1.  매칭된 부모의 `standard_sub_chunks`를 SQLite에서 전체 열거.
    2.  각 표준 서브청크에 대해 사용자 서브청크 중 임계값 이상 매칭이 **하나라도** 있는지 확인.
    3.  미커버(uncovered) 표준 서브청크가 존재하면 → 해당 부모 조항을 `Deviation.CHANGED`로 상향하여 2차 LLM에 전달.
*   **체크 범위: 조 내부(clause-local)로 한정.**
    *   사용자가 ⑩을 다른 조에 흩어 적었을 가능성은 1차에서 구분하지 않는다.
    *   "표준 ⑩ 미커버"를 `CHANGED` 신호로 올리면, 2차 LLM이 계약 전체 맥락에서 "사실 다른 조에 있다"를 판단한다. 이 경계가 규칙 #1(1차 해석 금지)과 일치한다.
    *   전체 계약 서브청크 대상 교차 탐색은 정밀도 향상이 불확실(다른 조의 유사 문구가 오매칭될 수 있음)하고 복잡도만 높아지므로 채택하지 않는다.
*   **코드 파일:** [review_pipe.py](../../src/pipe/review_pipe.py) 또는 신규 `core/coverage.py` 순수함수.

### 4단계: 이탈 판정 임계값 (보조 역할만)

*   삭제 탐지의 주 메커니즘은 3단계 커버리지 체크이며, 임계값 조정은 **marginal 케이스 보조 수단**으로만 쓴다.
*   `change_threshold`를 높여도 9/10 항 일치 시나리오(삭제된 항이 1개)에서는 통과하므로, 임계값에 삭제 탐지를 기대하지 않는다.
*   **코드 파일:** [review_pipe.py](../../src/pipe/review_pipe.py) 내 기존 `change_threshold` 유지.

---

## 3. 평가 체계 (Ablation 및 골든셋 검증)

*   **골든셋 확장:**
    *   거대 조항 내 특정 핵심 항을 부분 삭제하거나 다른 불리한 내용으로 합성 변형한 케이스(예: 제58조 하도급 대금 조항 ⑩ 삭제 변형본)를 골든셋 데이터에 추가.
*   **Ablation 실험 설계:**
    *   **비교군 A (Baseline):** 조 단위 통째 임베딩 및 검색
    *   **비교군 B (Proposed):** 거대 조항 대상 조건부 서브청킹 + Max 롤업 + 커버리지 체크
*   **측정 지표 (규칙 #5 — 결정론적·재현 가능):**
    *   **Coverage Recall**: 삭제된 표준 항을 "미커버"로 잡아내는 비율 (주 지표)
    *   F1-Score / Recall@k: 비교군 간 전체 탐지율 비교
    *   LLM-judge 사용 금지.
*   **코드 파일:** [ablation.py](../../eval/ablation.py) — 청킹·롤업·커버리지 체크 전략 비교 실험 하니스 구성.

---

## 4. 완료 조건 (DoD)

- [x] `01.CREATE_TABLE.sql`에 `standard_sub_chunks` 테이블 추가 및 `models.py`에 `StandardSubChunk` 모델 추가
- [x] 거대 조항 분할 조건(500자 초과 OR 항·호 기호 3개 이상) `build_index.py` 반영 + SQLite·Chroma 적재 검증
- [ ] `vector_manager.py` Max Roll-up 검색 로직 구현 및 단위 테스트 통과
- [ ] `review_pipe.py`(또는 `core/coverage.py`) 커버리지 체크 로직 구현 및 단위 테스트 통과
- [ ] 거대 조항 "항 삭제" 변형 골든셋 구축 완료
- [ ] Ablation Before/After에서 Coverage Recall 개선 수치 증명
