"""
[Phase 0] SQLite 마이그레이션 + normalized 적재 진입점

`just migrate` (또는 `just build-db`의 첫 단계)로 실행됩니다.
역할:
  1. data/migration/01.CREATE_TABLE.sql 스키마 적용
  2. data/03_normalized/*.json 을 pydantic 으로 검증 후 SQLite 에 적재

결정론적 재생성을 위해 기존 contract.sqlite3 를 삭제하고 처음부터 다시 만듭니다.
(normalized JSON/SQL = 진실의 원천, SQLite = 재생성 파생물 — data/README.md 참고)

⚠ enum 에 없는 값이 normalized 에 있으면 pydantic 검증에서 즉시 실패합니다(빠른 실패).
"""
import sys
import json
import sqlite3
import logging
from pathlib import Path

# config / contracts 를 import 하기 위해 src/ 를 모듈 경로에 추가 (실행 위치 무관)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BASE_DIR, DB_BASE_FILE
from contracts.models import StandardClause, ClauseRelation, ToxicPatternRecord

logging.basicConfig(level=logging.INFO, format="%(message)s")

SCHEMA_FILE = BASE_DIR / "data" / "migration" / "01.CREATE_TABLE.sql"
NORMALIZED_DIR = BASE_DIR / "data" / "03_normalized"
DB_PATH = BASE_DIR / DB_BASE_FILE


def _load_normalized(filename: str) -> list[dict]:
    """normalized JSON 파일을 읽어 dict 리스트로 반환합니다. 없으면 빈 리스트."""
    path = NORMALIZED_DIR / filename
    if not path.exists():
        logging.warning(f"⚠ normalized 파일 없음(건너뜀): {path.name}")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def migrate() -> None:
    """스키마를 적용하고 모든 normalized 를 검증·적재합니다."""
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"스키마 파일을 찾을 수 없습니다: {SCHEMA_FILE}")

    # 1. 결정론적 재생성: 기존 DB 파일 제거
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
        logging.info(f"🗑  기존 DB 삭제: {DB_PATH.name}")

    conn = sqlite3.connect(DB_PATH)
    try:
        # 2. 스키마 적용
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        logging.info(f"📐 스키마 적용 완료: {SCHEMA_FILE.name}")

        # 3. 표준조항 적재 (standard_clauses.*.json 전체)
        clause_rows = []
        for normalized_file in sorted(NORMALIZED_DIR.glob("standard_clauses.*.json")):
            for raw in json.loads(normalized_file.read_text(encoding="utf-8")):
                c = StandardClause(**raw)  # enum/필수필드 검증
                clause_rows.append(
                    (c.clause_id, c.contract_type.value, c.category.value,
                     c.title, c.text, c.source, c.version)
                )
        conn.executemany(
            "INSERT INTO standard_clauses "
            "(clause_id, contract_type, category, title, text, source, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            clause_rows,
        )
        logging.info(f"📄 표준조항 {len(clause_rows)}건 적재")

        # 4. 의존성 그래프 엣지 적재
        relation_rows = [
            (r.source_category.value, r.target_category.value, r.relation_type.value)
            for raw in _load_normalized("clause_relations.json")
            for r in [ClauseRelation(**raw)]
        ]
        conn.executemany(
            "INSERT INTO clause_relations "
            "(source_category, target_category, relation_type) VALUES (?, ?, ?)",
            relation_rows,
        )
        logging.info(f"🔗 의존성 엣지 {len(relation_rows)}건 적재")

        # 5. 독소조항 패턴 적재
        toxic_rows = [
            (t.pattern_id, t.pattern.value,
             t.category.value if t.category else None, t.title, t.text)
            for raw in _load_normalized("toxic_patterns.json")
            for t in [ToxicPatternRecord(**raw)]
        ]
        conn.executemany(
            "INSERT INTO toxic_patterns "
            "(pattern_id, pattern, category, title, text) VALUES (?, ?, ?, ?, ?)",
            toxic_rows,
        )
        logging.info(f"☠  독소조항 패턴 {len(toxic_rows)}건 적재")

        conn.commit()
        logging.info(f"\n✅ 마이그레이션 완료 → {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
