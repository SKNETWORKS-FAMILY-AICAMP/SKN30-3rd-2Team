from unittest.mock import MagicMock, patch
import pytest
from contracts.enums import ContractType, ProgressPhase, Deviation
from contracts.models import DeviationResult
from server.dto import ReviewContractResponse
from server.server import review_contract

class FakeContext:
    def __init__(self):
        self.progress_reports = []

    async def report_progress(self, done: int, total: int, message: str):
        self.progress_reports.append((done, total, message))

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
@patch("server.server.get_parser")
@patch("server.server._load_standards")
@patch("server.server._load_sub_chunks")
@patch("server.server.review_contract_pipe")
async def test_review_contract_async_progress(
    mock_pipe, mock_load_sub_chunks, mock_load_standards, mock_get_parser
):
    # 1. Mock 설정
    mock_parser = MagicMock()
    mock_parser.parse.return_value = ["fake_clause_1", "fake_clause_2"]
    mock_get_parser.return_value = mock_parser

    mock_load_standards.return_value = ["fake_standard"]
    mock_load_sub_chunks.return_value = {}

    fake_result = DeviationResult(
        user_clause="fake_clause_1",
        matched_standard=None,
        deviation=Deviation.NONE,
        confidence=1.0,
        grounding=[],
        toxic_patterns=[],
        related_risk_clauses=[],
        uncovered_sub_chunk_ids=[]
    )

    def fake_pipe(clauses, contract_type, retriever, embedder, reranker, grounder, all_standard_clauses, all_standard_sub_chunks, progress_callback=None):
        if progress_callback:
            progress_callback(0, 2, ProgressPhase.PREPARE)
            progress_callback(0, 2, ProgressPhase.BATCH_SEARCH)
            progress_callback(0, 2, ProgressPhase.RERANK)
            progress_callback(1, 2, ProgressPhase.CLAUSE_REVIEW)
            progress_callback(2, 2, ProgressPhase.CLAUSE_REVIEW)
            progress_callback(2, 2, ProgressPhase.MISSING_DETECTION)
        return [fake_result]

    mock_pipe.side_effect = fake_pipe

    # 2. 실행
    ctx = FakeContext()
    response = await review_contract(
        contract_type="SW_FREELANCE",
        file_path="/dummy/path.pdf",
        ctx=ctx
    )

    # 3. 검증
    assert response.status == "OK"
    assert len(response.results) == 1
    assert response.results[0].user_clause == "fake_clause_1"
    assert response.results[0].deviation == Deviation.NONE

    # progress 보고가 올바른 순서와 메시지로 전송되었는지 검증
    assert ctx.progress_reports == [
        (0, 2, "검토 준비 중..."),
        (0, 2, "벡터 DB 배치 검색 중..."),
        (0, 2, "조항별 재정렬 중..."),
        (1, 2, "조항별 이탈 분류 중... (1/2)"),
        (2, 2, "조항별 이탈 분류 중... (2/2)"),
        (2, 2, "누락 표준조항 분석 중..."),
    ]

