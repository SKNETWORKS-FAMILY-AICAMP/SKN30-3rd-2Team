from typing import Dict, List, Set

def traverse_related_risks(
    adjacency_list: Dict[str, List[str]],
    deviated_clause_id: str,
    max_depth: int = 3
) -> List[str]:
    """
    [고도화 A: 계약-조항 의존성 그래프]
    CHANGED·MISSING 이탈이 확정된 조항에 대해, 연쇄적으로 함께 검토해야 할
    표준조항 ID 목록을 반환합니다. DeviationResult.related_risk_clauses 필드를 채웁니다.

    adjacency_list는 data/03_normalized/clause_relations.json을 파이프가 메모리에
    로드한 구조입니다(clause_id → [연관 clause_id, ...]). 예를 들어 IP_OWNERSHIP 조항이
    이탈하면 DERIVATIVE_WORK·LIABILITY 관련 조항도 함께 검토 대상으로 올라옵니다.

    시작 노드(deviated_clause_id)는 이미 이탈로 확정됐으므로 결과에서 제외하고,
    그 조항과 연결된 노드들만 수집합니다.

    Args:
        adjacency_list: clause_id 기준 인접 리스트 (pipe가 JSON에서 로드해 주입)
        deviated_clause_id: 이탈이 확정된 표준조항의 clause_id
        max_depth: 탐색할 최대 깊이 (기본 3 — 직접·간접 연관까지)

    Returns:
        함께 검토해야 할 표준조항 clause_id 목록 (오름차순 정렬)
    """
    related_risks: Set[str] = set()
    visited: Set[str] = set()

    def dfs(node: str, depth: int):
        if depth > max_depth or node in visited:
            return
        visited.add(node)
        
        neighbors = adjacency_list.get(node, [])
        for neighbor in neighbors:
            if neighbor != deviated_clause_id:
                related_risks.add(neighbor)
            dfs(neighbor, depth + 1)

    dfs(deviated_clause_id, 1)
    return sorted(list(related_risks))
