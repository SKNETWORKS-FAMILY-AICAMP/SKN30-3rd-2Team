# [불가결 G] 레버 비교 설계
**조항 내 미시적 구성요소(Element) 정렬 및 법률 레버(Lever) 규칙 기반 이탈 탐지 고도화**

---

## 0. ⛔ 선행 조건 — 동결 계약 변경 승인 요청 (구현 전 필수)

> AGENTS.md 절대 규칙 #2: *동결 계약(조항 스키마·MCP 시그니처)을 임의 변경 금지. 변경이 필요하면 코드 수정 전에 사람에게 먼저 물을 것.*
> 본 설계는 동결된 [`enums.py`](../../src/contracts/enums.py)·[`models.py`](../../src/contracts/models.py)에 변경을 요구한다. **아래 3건이 사람 승인을 받기 전에는 코드를 수정하지 않는다.** (a)/(b)/(c)는 쪼개지 않고 **한 묶음으로 일괄 승인**한다 — "필드 추가는 가벼우니까"라는 예외를 만들면 규칙 #2가 무너진다.

### 변경 안건 (3건, 일괄 승인 요청)

| # | 안건 | 형태 | 비고 |
| --- | --- | --- | --- |
| (a) | `DeviationResult.granularity: Literal[CLAUSE, ELEMENT] = CLAUSE` 추가 | **가법·하위호환** | 기존 조 단위 결과는 기본값으로 그대로 동작 |
| (b) | `DeviationResult.change_kind: Optional[ChangeKind] = None` 추가 (`ChangeKind = WEAKENED \| NUMERIC \| MODALITY \| ACTOR \| EXCEPTION`) | **가법·하위호환** | `CHANGED` 판정의 세부 사유를 속성으로 표현 |
| (c) | element 정렬쌍·판정을 담는 하위 결과 모델(`ElementResult`) 신설 + `DeviationResult.elements: List[ElementResult] = []` 로 매닲 | **가법·하위호환** | 5단계 산출물의 그릇. 기존 소비자는 빈 리스트로 무시 |

### 기각한 대안 (참고용 — 사람 판단 근거)
- ❌ `Deviation` enum 에 `ELEMENT_MISSING` / `ELEMENT_WEAKENED` / `NUMERIC_VIOLATION` **신설**.
  - **비하위호환**: `Deviation` 을 분기하는 모든 소비자(core·pipe·mcp_server·리포트)가 새 값 처리를 강제당함 → 분기 누락 시 규칙 #4(빈 응답·조용한 실패 금지) 위반의 씨앗.
  - **확장 시 반복 폭발**: SW_NDA·연동계약 등으로 계약유형이 늘 때마다 enum 이 또 터짐.
  - → 그래서 "누락"은 기존 `Deviation.MISSING` 을 재사용하고 `granularity` 로 조/원소를 구분하고, "약화·수치"는 `Deviation.CHANGED` + `change_kind` 속성으로 접는다. (F_graph 가 `traverse_related_risks` 를 재사용한 것과 동일 원칙)

### `standard_elements` / 신규 enum
1단계의 `standard_elements` 테이블, `StandardElement` 모델, `Beneficiary`(아래 5단계) 등 신규 enum 도 동일하게 본 승인 안건에 포함된다. 표준 조 단위 스키마([`StandardClause`](../../src/contracts/models.py#L16))는 **변경하지 않고**, element 는 별도 테이블·모델로 신설한다.

---

## 1. 배경 및 목적
*   **기존 조 단위 RAG의 한계:**
    기존의 조(Article) 단위 검색 매칭은 조항 본문 내에서 특정 항(①②)이나 호(1.2.)가 통째로 삭제되거나 일부 문구만 미세하게 왜곡되었을 때 유사도 점수 평균화 효과에 의해 이를 안전하게 잡아내지 못하고 통과시키는 오탐 한계가 존재합니다.
*   **고도화 목적:**
    조항 내부를 의미적 최소 단위인 **원소(Element) 레벨로 분해**하고, 결정론적 정렬(임계값 기반 다대다)과 결정론적 규칙 비교(법률 레버 분해)를 적용하여 **재현 가능하고 정밀한 이탈 탐지**를 실현합니다.

---

## 2. 세부 단계별 아키텍처 및 구현 설계

### 1단계: 표준 조의 분해 및 필수항목 체크리스트 (오프라인, 1회성)
*   **목표:** 표준계약서 조항을 항(①②)·호(1.2.3.) 단위로 쪼개어 데이터베이스에 정답 원소로 적재합니다.
*   **스키마 구성 (`standard_elements` 신설 — 0장 승인 대상):**
    *   `parent_clause_id`: 상위 조항 식별자 (예: `sw_freelance-art20`)
    *   `element_id`: 원소 고유 식별자 (예: `sw_freelance-art20-el02` / 항·호 번호 기반)
    *   `text`: 분해된 개별 문장 텍스트
    *   `beneficiary`: **이 항의 이익이 누구에게 귀속되는가** (`SUBCONTRACTOR` 수급사업자 / `PRINCIPAL` 원사업자 / `MUTUAL` 쌍방) — 5장 심각도 연산의 입력. (구 `protects` 의 의미 모호 정정: "보호 의도"가 아니라 "수혜 당사자" 축으로 확정)
    *   `polarity`: 조항의 지향성 (`PROTECTIVE` 보호 / `RESTRICTIVE` 제약)
    *   `required`: 필수 여부 (`True` / `False`)
    *   `grounding_ref`: 매핑 법령 조문 좌표 (예: `하도급법 제13조`)
*   **수행 방식:** 오프라인 준비 단계에서 LLM으로 초안을 추출하되, **사람이 검수하여 `data/03_normalized` 에 git 동결**한다. 런타임에는 LLM을 호출하지 않으므로 규칙 #1(1차 런타임 LLM 호출 금지) 위반이 아니다. 동결된 정적 코퍼스이므로 런타임 환각이 발생하지 않는다.

### 2단계: 사용자 조의 분해 (런타임)
*   **목표:** 검토 대상인 사용자 계약서의 조항을 런타임에 동일한 크기로 분해합니다.
*   **규칙 기반 분할:**
    *   **식별 기호 분기:** 문장 내 항 번호(`①`, `②` 등) 및 호 번호(`1.`, `2.` 등)가 명시된 경우 정규식을 통해 분해합니다.
    *   **줄글 분기:** 번호 체계가 없는 자유 서식 문장인 경우, 한국어 문장 분할기(`kss`)와 접속어 및 연결어미 패턴(`다만,`, `~하며,`, `~제외`)을 감지하여 명제 단위로 슬라이싱합니다.
    *   **재현성 확보:** `kss` 는 사전·통계 기반이라 "규칙 기반"은 아니지만 **동일 입력에 결정론적**이다. 따라서 평가 재현성을 위해 **버전을 고정**(`kss==<x.y.z>`)하고, 정규식·패턴 사전과 함께 런타임 동작을 동결한다.

### 3단계: 임계값 기반 다대다 정렬 (Element Alignment)
*   **목표:** 사용자 분할 명제들과 표준 `standard_elements` 간의 정렬 관계를 결정론적으로 도출합니다.
*   **정렬 방식 정정:** 기존 안의 "다대다 최적 정렬 + 헝가리안(`linear_sum_assignment`)"은 **모순**이다. 헝가리안은 엄격한 **1:1 할당**이라, 하도급 본문에서 가장 흔한 **1:N**(표준 한 항을 사용자가 여러 문장으로 풂)·**N:1**(사용자가 여러 항을 한 문장에 뭉침)을 1:1로 풀면 잔여분을 강제로 `MISSING`/`EXTRA` 로 떨궈 **이 설계가 잡으려던 오탐을 역으로 만든다.** → 아래 두 방식 중 채택:
    *   **(채택) 임계값 기반 다대다 매칭:** 각 표준 element 에 대해 임계값 이상 점수를 갖는 사용자 명제를 **모두** 연결한다(1:N·N:1 자연 허용). 코퍼스가 작아 최적성보다 **재현성·단순성**이 더 값지다.
    *   **(대안) 1:1 최적 정렬 + 잔여 흡수 패스:** 헝가리안으로 1차 1:1 할당 후, 남은 사용자/표준 단위를 임계값 위에서 추가 흡수하는 2차 그리디 패스로 1:N 을 허용. 복잡도가 더 높아 본 설계의 기본값은 아니다.
*   **메커니즘:**
    1.  **후보 압축:** 하이브리드 검색([`Retriever`](../../src/contracts/ports.py#L54))으로 표준 element 후보를 압축한다 (element 레벨 인덱싱 필요 → B_index 연계).
    2.  **Reranker 스코어링:** `bge-reranker-v2-m3`([`Embedder.compute_similarity`](../../src/contracts/ports.py#L42)) 로 (사용자 명제 × 후보 element) 교차 점수 행렬을 채운다.
    3.  **임계값 매칭:** 임계값 이상 쌍을 정렬 관계로 확정한다.
*   **판정 도출:**
    *   매칭된 표준 element 가 0개인 **필수(`required`) element** ➔ `Deviation.MISSING` + `granularity=ELEMENT` (예: 거대 조에서 특정 항만 삭제된 사례)
    *   어떤 표준 element 에도 붙지 않은 사용자 명제 ➔ `Deviation.EXTRA` + `granularity=ELEMENT` (추가/독소조항 후보)
    *   정렬된 쌍 ➔ 4단계 분석으로 전달

### 4단계: 매칭된 쌍의 의미적 차이 추출 ("법률 레버" 분해)
*   **목표:** 정렬된 표준-사용자 명제 쌍을 대상으로 법률적 구속력의 강도 변화를 룰베이스로 비교합니다.
*   **4대 법률 레버(Lever) 감지 (결정론적 규칙):**
    1.  **양태 (Modality):** `할 수 있다`(권리) / `하여야 한다`(의무) / `하지 아니한다`(금지·배제)의 뒤집힘 추적
    2.  **부정 및 예외 (Exception):** `다만,`, `~경우에는`, `~을 제외하고는` 등 면책 조건 추적
    3.  **당사자 (Actor):** 권리·의무가 부여되는 주체(`원사업자` vs `수급사업자`)의 주객 전도 추적
    4.  **수치 (Numeric Limit):** 대금 지급 기한(60일), 이율, 지연이자율 등 한계선 추적
*   **판정 매핑 (enum 신설 없이 기존 값 재사용):**
    *   양태/당사자 반전(표준은 수급자 권리인데 사용자 조에서 원사업자 권리로 이양 등) ➔ `Deviation.CHANGED` + `change_kind=WEAKENED|MODALITY|ACTOR`
    *   하드 넘버 위반(대금 60일·지연이자율 한도 등을 Regex 로 추출 대조) ➔ `Deviation.CHANGED` + `change_kind=NUMERIC`
*   **NLI 보조 신호 (규칙 #1 경계 명시):**
    *   `KLUE-NLI` 로 표준 element(전제) vs 사용자 명제(가설)의 `Entailment / Neutral / Contradiction` 을 추론한다. NLI **추론 자체**는 결정론적 분류라 규칙 #1("분류만" 허용)·#5(LLM-judge 아님)를 형식상 통과한다.
    *   ⚠️ 그러나 **"Contradiction → 불리한 변경" 매핑**은 규칙 #1이 금지한 "불리함 판단 생성"에 닿는 **경계**다. 따라서:
        *   NLI 는 **신호 1개로만** 쓰고, 최종 불리/심각 판정은 **양태·당사자·수치 규칙**으로 내린다.
        *   "Contradiction→불리" 매핑 채택 여부는 **사람 확인 대상**으로 남기고, **측정(Ablation)으로 기여가 입증될 때만** 활성화한다.

### 5단계: 불리함의 방향 및 심각도 평가 + 법리 근거 바인딩 (Grounding)
*   **불리함의 정의:** `beneficiary == SUBCONTRACTOR` 이고 `polarity == PROTECTIVE` 인 element 의 **누락(MISSING) 또는 약화(CHANGED/WEAKENED)** 를 "수급사업자에게 불리"로 정의한다.
*   **심각도 결정표 (결정론적 룩업 — 규칙 #5 충족):** 추상적 "태그 연산" 대신 고정 매핑표로 산출한다.

    | required | beneficiary | deviation / change_kind | severity |
    | --- | --- | --- | --- |
    | True | SUBCONTRACTOR | MISSING(element) | **HIGH** |
    | True | SUBCONTRACTOR | CHANGED / WEAKENED·MODALITY·ACTOR | **HIGH** |
    | True | SUBCONTRACTOR | CHANGED / NUMERIC (하드넘버 위반) | **HIGH** |
    | False | SUBCONTRACTOR | MISSING / CHANGED | **MEDIUM** |
    | * | PRINCIPAL | EXTRA (원사업자 이익 추가) | **MEDIUM** |
    | * | MUTUAL | * | **LOW** |
    | * | * | NONE | — |

    > 위 표는 초안이며, 가중치·등급 경계는 골든셋 측정으로 보정한다. 핵심은 **입력(required, beneficiary, polarity, deviation, change_kind)이 결정론적으로 severity 로 사상**된다는 점.
*   **법리 Grounding:** `grounding_ref` 의 법조문을 기반으로 `korean-law-mcp`([`Grounder`](../../src/contracts/ports.py#L73))를 호출해 위반 근거 조문(예: 하도급법 제13조)을 리포트에 바인딩한다.

---

## 3. 평가 체계 (Ablation 및 골든셋 수립)
*   **골든셋의 해상도 고도화:**
    골든셋 데이터 구조를 (사용자 명제 ↔ 표준 Element) 정렬 쌍과 Element별 이탈 판정 라벨로 세분화한다. element 정답 정렬은 수작업 라벨링 부담이 크므로 범위를 한 조에 집중해 시작한다.
*   **특수 파괴 테스트 케이스 (데이터 보유 계약유형으로 이전):**
    대표 케이스를 **`SW_FREELANCE` 본문의 거대 조 내 "특정 항만 쏙 뺀 케이스"** 로 잡는다. `data/03_normalized` 에 표준 코퍼스가 있는 계약유형으로 먼저 메커니즘을 증명한다(구 안의 `sw_subcontract-art58` 은 표준 코퍼스가 아직 없어 대표 케이스 부적격).
    *   단순 조 단위 RAG 의 '유사도 통과 오류'를 이 미시 파이프라인이 element `MISSING` 으로 구제하는지를 Ablation Before/After 수치로 모니터링한다.
    *   **SW_SUBCONTRACT(하도급 본문) 케이스는 표준 코퍼스 확보를 선행 조건으로 명시하고 그 전까지 보류** — 하도급은 2차 1순위 확장과 일관.
*   **재현성 통제:**
    결과 평가에 일절 LLM-judge 를 도입하지 않고 정량 F1-Score·Recall 만 산출한다(규칙 #5).

---

## 4. 완료 조건 (DoD)
- [ ] **0장 동결 계약 변경 3건(+`standard_elements`·신규 enum)에 대해 사람 승인 완료** — 이전엔 코드 미수정
- [ ] `standard_elements` 적재 + element 레벨 인덱싱(B_index 연계)
- [ ] 2단계 규칙 분할기 + `kss` 버전 고정으로 동일 입력 결정론 재현 확인
- [ ] 3단계 임계값 기반 다대다 정렬로 1:N·N:1 케이스에서 오탐 미발생 확인
- [ ] 4단계 4대 레버 룰 + (측정 통과 시) NLI 보조 신호
- [ ] 5단계 심각도 결정표로 severity 결정론 산출, `grounding_ref` 바인딩
- [ ] freelance 거대 조 "항 삭제" 골든셋에서 Ablation Before/After 개선 입증

---

## 5. 기존 작업 영향 및 선후 의존

> 핵심: 0장을 **가법·하위호환**으로 설계한 덕에 기존 코드를 "깨는" 소비자는 사실상 없고, 대부분 "추가/분기"다. 단 토대가 되는 미구현 태스크(C·D)와 인덱스 확장(B)이 선후 의존을 만든다.

### 영향 요약

| 레이어 | 강도 | 성격 |
| --- | --- | --- |
| contracts (동결) | 🔴 변경 필요 | **가법적**(0장 승인 전제) — 기존 필드/enum 불변 |
| DB 스키마·데이터 | 🟠 신설 | 기존 테이블 불변, `standard_elements` 추가 |
| pipe (review/index/normalize) | 🟠 확장 | 기존 조 단위 경로 유지 + element 경로 분기 |
| core | 🟡 추가 | 기존 순수함수 불변, 신규 정렬 모듈 추가 |
| server/MCP·DTO | 🟢 자동 전파 | 코드 수정 거의 없음 (가법 필드 자동 상속) |
| eval | 🟠 해상도 변경 | 골든셋 구조·지표 입력 변경 |

### ⚠️ 선행 의존 (구현 순서 강제)
- **C(review_pipe) 선행:** [review_pipe.py](../../src/pipe/review_pipe.py) 가 아직 `NotImplementedError`. G 는 조 단위 검토 흐름 **위에 element 분기를 얹는** 구조라, C 가 동작하지 않으면 토대가 없다. → **순서: C → G.**
- **B(index) 연계:** [build_index.py](../../src/pipe/build_index.py) 는 현재 `standard_clauses`·`toxic_patterns` 컬렉션만 인덱싱. G 는 **element 레벨 Chroma 컬렉션 신설**이 필요(3단계 후보 압축).
- **D(eval) 병행:** [ablation.py](../../eval/ablation.py) `run_ablation` 미구현. G 의 "Before/After 오탐 구제" 검증이 D 위에 얹힘.

### 레이어별 상세
- **contracts:** [DeviationResult](../../src/contracts/models.py#L66) 에 `granularity`·`change_kind`·`elements` 추가(기본값으로 기존 생성 코드 전부 동작). `ChangeKind`·`Beneficiary` enum 과 `StandardElement` 모델 신설. 기존 `Deviation`·`Category` 불변.
- **DB/데이터:** [01.CREATE_TABLE.sql](../../data/migration/01.CREATE_TABLE.sql) 에 `standard_elements` 테이블 추가(기존 3개 불변). `data/03_normalized/` 에 element 정답 JSON 신규. [0.migrate.py](../../src/pipe/0.migrate.py)·`just build-db` 확장.
- **core:** [matching.select_best_match](../../src/core/matching.py#L4)(1:1·조 단위)·[deviation.classify_clause_deviation](../../src/core/deviation.py#L14) 는 **그대로 두고**, element 정렬·레버 판정은 신규 순수함수로 추가(TDD: 새 테스트부터). 기존 `test_matching`·`test_deviation` 영향 없음.
- **server/MCP/DTO:** [dto.ReviewContractResponse](../../src/server/dto.py#L35) 가 `DeviationResult` 를 담으므로 **가법 필드가 자동 직렬화** — DTO 수정 불필요. [server.review_contract](../../src/server/server.py#L181) 툴 시그니처 불변 → **MCP 동결 계약(4장) 영향 없음.**
- **eval:** 골든셋이 (사용자 명제 ↔ Element) 정렬쌍 + element 라벨로 세분화 → `metrics.py`·`run_eval` 입력 스키마 변경, 관련 테스트 영향. 규칙 #5(F1/Recall, LLM-judge 금지)는 양쪽 일치.

### 타 태스크 연계 (충돌 없음)
- **F_graph:** `related_risk_clauses` 는 clause_id 레벨. element MISSING 을 `parent_clause_id` 로 환원해 그래프에 먹임 — 소폭 통합.
- **E_toxic:** element `EXTRA`(독소 후보)가 toxic_patterns 검색으로 연결 — 보완 관계.
- **grounding:** element 별 `grounding_ref` 가 [Grounder](../../src/contracts/ports.py#L73) 에 더 정밀한 조문 바인딩 입력 제공 — 기존 category 경로와 공존.

### 비용·리스크 (기능 외)
- **런타임 지연:** element × 후보 reranker 교차 점수는 O(N×M) — 조 단위보다 호출 증가. 하이브리드 후보 압축으로 완화하되 응답 시간 증가 측정 필요.
- **라벨링 비용:** element 정렬 골든셋 수작업 부담 → freelance 한 조로 범위 한정(3장 반영).
- **임계값 2종화:** 기존 `match_threshold=0.5`(조 단위)와 별개로 element 정렬 임계값 추가 → 튜닝 표면 증가.
