# MCP 서비

추후 다음과 같이 구현
```
# src/server/app.py (예시)
from contracts.implement import KordocParser
from pipe.review_pipe import review_contract
from adapter import vector, koreanLaw

@mcp.tool()
def review_contract_file(file_path: str, contract_type: str) -> List[DeviationResult]:
    # 1. 파일에서 조항 리스트로 변환 (KordocParser 사용)
    parser = KordocParser()
    clauses = parser.parse(file_path)  # List[Clause] 변환 발생!
    
    # 2. 전 조항에서 비교 대조할 표준 조항 리스트 DB에서 로드
    all_standards = db.load_standards(contract_type)
    
    # 3. 파이프라인 구동
    results = review_contract(
        clauses=clauses,
        contract_type=contract_type,
        retriever=vector,
        grounder=koreanLaw,
        all_standard_clauses=all_standards
    )
    return results
```