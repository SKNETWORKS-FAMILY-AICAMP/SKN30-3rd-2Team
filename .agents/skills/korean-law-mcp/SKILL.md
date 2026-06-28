---
name: korean-law-mcp
description: 대한민국 법령 및 판례 리서치/분석을 위한 [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) CLI 및 도구를 사용하는 에이전트의 행동 지침
---
## 1. 목적 및 개요

본 기술 지침은 대한민국 법령, 행정규칙, 자치법규, 판례, 해석례 등을 검색하고 정밀 분석하기 위해 [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) CLI 및 도구를 사용하는 에이전트의 행동 지침이다. 에이전트는 법률적 환각(Hallucination)을 완전히 방지하고, 실시간 CLI 조회를 통해 신뢰할 수 있는 법률 검토 의견서를 작성해야 한다.

---

## 2. CLI 환경 설정 및 기본 명령어

### 💻 핵심 CLI 명령어 레퍼런스

* **자연어 직접 조회 (가장 빠름):**
```bash
korean-law "민법 제1조"
korean-law "음주운전 처벌 기준 판례"

```


* *팁:* 복잡한 옵션 없이 자연어나 조문을 직접 입력하면 AI가 내부적으로 최적의 도구를 선택해 즉시 결과를 반환한다.


* **특정 도구 직접 호출 (하위 파라미터 제어):**
```bash
korean-law search_law --query "관세법"
korean-law cite_check --caseNumber "2022도1234"

```


* **도구 탐색 및 도움말:**
```bash
korean-law list                        # 사용 가능한 전체 도구 목록
korean-law list --category 판례          # 법령, 행정규칙, 자치법규, 판례 등 필터링
korean-law help search_law             # 특정 도구의 상세 파라미터 및 설명 확인

```



---

## 3. 마스터 진입점 (상세 분석 및 태스크용)

복잡한 다단계 리서치나 팩트 체크가 필요할 때는 CLI 명령어 뒤에 `legal_research` 또는 `legal_analysis` 도구를 지정하여 상세 옵션을 실행한다.

### 🔍 A. 다단계 종합 리서치 (`korean-law legal_research`)

* **사용법:** `korean-law legal_research --query "검색어" --task "태스크명"`
* **주요 태스크 (`--task`):**
* `full_research`: 종합 리서치 (AI 검색 → 법령 → 판례 → 해석례 자동 수행)
* `law_system`: 법체계 파악 (법령 검색 → 3단 비교 → 조문 일괄 조회)
* `action_basis`: 처분/허가 근거 확인 (법체계 → 해석례 → 판례 → 행정심판)
* `procedure_detail`: 절차/비용/서식 확인 (법체계 → 별표 및 서식 추출)



### ⚖️ B. 정밀 분석 및 검증 (`korean-law legal_analysis`)

* **사용법:** `korean-law legal_analysis --mode "모드명" [추가옵션]`
* **주요 모드 (`--mode`):**
* `verify_citations`: **[환각 방지]** 에이전트 본문 내 조문 인용을 추출하여 법제처 DB와 교차 검증
* `cite_check`: **[판례 생사 확인]** 전원합의체 변경/폐기 여부 실시간 감지
* `applicable_law`: **[행위시법 판단]** 과거 특정 기준일 시행 버전의 부칙/경과조치 발췌 비교



---

## 4. 핵심 규칙 및 제약 사항 (Crucial Rules)

### 🔴 규칙 1: 조문 번호(JO 코드) 포맷 준수 (AAAABB 형식)

도구 직접 호출 방식으로 조문을 조회할 때 `--jo` 파라미터는 반드시 **6자리 문자열 코드** 형식으로 변환해야 한다. (자연어 조회 시에는 제외)

* `제5조` ➔ `"000500"`
* `제38조` ➔ `"003800"`
* `제10조의2` ➔ `"001002"` (가지번호는 뒤 2자리에 매핑)

### 🔴 규칙 2: 고유 ID 체계 매핑

검색 결과 파싱 후 다음 단계 명령어로 아이디를 넘길 때 올바른 키값을 매핑해야 한다.

* **법령:** `mst` (6자리, 예: 279811) 또는 `lawId` (6자리)
* **행정규칙:** `id` (13자리, 예: 2100000261222)
* **판례 / 해석례:** `id` (6자리)

---

## 5. 추천 연계 워크플로우 (kordoc CLI와 연계)

### 🔗 패턴: 행정규칙 서식 추출 및 문서 자동 채우기

1. **법률 서식 검색:** ```bash
korean-law legal_research --query "고용보험 시행규칙 서식" --task "procedure_detail"
```

```


2. **별표/서식 코드 확인:** 출력된 결과에서 원하는 신청서 양식의 `bylSeq` 번호를 식별한다.
3. **양식 내용 다운로드:** 해당 서식의 raw 텍스트나 HWPX 경로를 확보한다.
4. **문서 자동 생성 (kordoc 연계):** 획득한 서식 구조를 기반으로 사용자 데이터를 바인딩하여 터미널에서 최종 한글 문서를 빌드한다.
```bash
npx kordoc fill 템플릿.hwpx -f '성명=홍길동,신청일자=2026-06-28' -o 제출용_신청서.hwpx

```