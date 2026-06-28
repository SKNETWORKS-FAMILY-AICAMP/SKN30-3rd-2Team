from typing import Dict, List, Set

def traverse_related_risks(
    adjacency_list: Dict[str, List[str]],
    deviated_clause_id: str,
    max_depth: int = 3
) -> List[str]:
    """
    [고도화 A: 계약-조항 의존성 그래프]
    이탈(Deviation)이 발생한 조항으로부터 인접 리스트를 DFS 탐색하여 
    연쇄적으로 함께 검토해야 할 연관 표준 조항 ID 목록을 추론 및 반환합니다.
    (I/O 없이 메모리 구조에서 순수 알고리즘으로 동작합니다.)
    
    Args:
        adjacency_list (Dict[str, List[str]]): 노드(조항 ID) 간 인접 리스트
        deviated_clause_id (str): 이탈이 감지된 조항의 ID
        max_depth (int): 탐색할 최대 그래프 깊이
        
    Returns:
        List[str]: 함께 검토해야 할 연관 조항 ID 목록 (오름차순 정렬)
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
