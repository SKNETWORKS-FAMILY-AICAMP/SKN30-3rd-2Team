-- =================================================================
-- WorkShield 표준조항 코퍼스 스키마 (기획서 3장 동결 / 7장 고도화)
--
-- ⚠ 이 파일과 data/03_normalized/*.json 이 "정답의 원천"입니다. (git 관리)
--   SQLite/Chroma 파일은 `just build-db` 로 여기서 재생성되는 파생물이며,
--   git 으로 관리하지 않습니다. (data/README.md 참고)
--
-- 모든 enum 컬럼 값은 src/contracts/enums.py 의 정의와 일치해야 합니다.
-- =================================================================

-- -----------------------------------------------------------------
-- 1) 표준조항 (기획서 3.1) — 비교 기준이 되는 "정답" 코퍼스
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS standard_clauses (
    clause_id     TEXT PRIMARY KEY,   -- 조항 고유 식별자 (예: sw_freelance-art20)
    contract_type TEXT NOT NULL,      -- ContractType enum (예: SW_FREELANCE)
    category      TEXT NOT NULL,      -- Category enum (예: IP_OWNERSHIP)
    title         TEXT NOT NULL,      -- 조항 제목 (예: 지식재산권의 귀속)
    text          TEXT NOT NULL,      -- 조항 본문
    source        TEXT NOT NULL,      -- 출처 좌표 (파일명 / 조번호)
    version       TEXT NOT NULL       -- 표준계약서 판/개정 버전
);

CREATE INDEX IF NOT EXISTS idx_std_contract_type ON standard_clauses(contract_type);
CREATE INDEX IF NOT EXISTS idx_std_category      ON standard_clauses(category);

-- -----------------------------------------------------------------
-- 2) 조항 의존성 그래프 엣지 (기획서 7.1) — category 레벨 연관
--    예: IP_OWNERSHIP 이탈 시 DERIVATIVE_WORK·LIABILITY 도 함께 검토
--    ports.py Graph.add_relation(source_category, target_category, relation_type) 와 일치
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clause_relations (
    source_category TEXT NOT NULL,    -- Category enum
    target_category TEXT NOT NULL,    -- Category enum
    relation_type   TEXT NOT NULL,    -- EdgeRelation enum
    PRIMARY KEY (source_category, target_category, relation_type)
);

-- -----------------------------------------------------------------
-- 3) 독소조항 패턴셋 (기획서 7.2) — 양방향 검색용 큐레이션 코퍼스
--    standard_clauses 와 별개로 Chroma 의 toxic_patterns 컬렉션에 임베딩됨
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS toxic_patterns (
    pattern_id TEXT PRIMARY KEY,      -- 패턴 고유 식별자 (예: toxic-ip_total_free-01)
    pattern    TEXT NOT NULL,         -- ToxicPattern enum
    category   TEXT,                  -- 연관 Category enum (nullable)
    title      TEXT NOT NULL,         -- 패턴 요약 제목
    text       TEXT NOT NULL          -- 독소조항 대표 문안 (검색 매칭 기준)
);

-- -----------------------------------------------------------------
-- 4) 거대 조항 서브청크 (기획서 고도화 G) — 커버리지 체크 및 롤업용
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS standard_sub_chunks (
    sub_chunk_id     TEXT PRIMARY KEY,  -- 예: sw_freelance-art58-sub01
    parent_clause_id TEXT NOT NULL,     -- FK → standard_clauses.clause_id
    sub_chunk_index  INTEGER NOT NULL,  -- 항 순서 (0-based)
    text             TEXT NOT NULL,
    contract_type TEXT NOT NULL,      -- ContractType enum (예: SW_FREELANCE)
    FOREIGN KEY (parent_clause_id) REFERENCES standard_clauses(clause_id)
);
CREATE INDEX IF NOT EXISTS idx_sub_parent ON standard_sub_chunks(parent_clause_id);
CREATE INDEX IF NOT EXISTS idx_sub_contract_type ON standard_sub_chunks(contract_type);
