import logging
import sqlite3
import threading
from config import DB_BASE_FILE

class DBManager:
    """
    SQLite 데이터베이스 연결 및 쿼리 실행을 관리하는 매니저 클래스입니다.
    팀원들은 이 클래스를 직접 인스턴스화하기보다 아래의 'db' 객체 사용을 권장합니다.
    """
    
    def __init__(self):
        # 멀티스레드(FastMCP 등) 환경에서의 커넥션 충돌을 방지하기 위해 thread-local 저장소를 사용합니다.
        self._local = threading.local()

    def connect(self):
        """데이터베이스 연결을 생성합니다. 이미 연결되어 있다면 기존 연결을 반환합니다."""
        try:
            if getattr(self._local, "connection", None) is None:
                db_path = DB_BASE_FILE
                # check_same_thread=False는 비동기 프레임워크나 스레드 스위칭 시 경고를 방지합니다.
                # threading.local을 통해 스레드 간 커넥션 객체가 물리적으로 격리되므로 안전합니다.
                self._local.connection = sqlite3.connect(db_path, check_same_thread=False)
                # 컬럼명을 키로 하는 딕셔너리 접근을 위해 sqlite3.Row 사용
                self._local.connection.row_factory = sqlite3.Row
            return self._local.connection
        except sqlite3.Error as e:
            logging.error(f"SQLite 연결 오류: {e}")
            raise

    def disconnect(self):
        """데이터베이스 연결을 안전하게 종료합니다."""
        conn = getattr(self._local, "connection", None)
        if conn:
            conn.close()
            self._local.connection = None

    def execute_query(self, query: str, params: tuple | list | dict | str | int | None = None) -> bool:
        """
        데이터 변경(INSERT, UPDATE, DELETE) 쿼리를 실행합니다.
        성공 시 True, 실패 시 False를 반환합니다.
        """
        if isinstance(params, (str, int, float, bool)):
            params = (params,)
        conn = self.connect()
        if not conn:
            return False
            
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"쿼리 실행 오류: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()

    def execute_many(self, query: str, params_list: list[tuple], chunk_size: int = 1000) -> int:
        """
        다량의 데이터를 한 번에 INSERT/UPDATE할 때 사용합니다. (배치 쿼리)

        Args:
            query (str): 실행할 쿼리 템플릿.
                         예) "INSERT INTO standard_clauses (category, text) VALUES (?, ?)"
            params_list (list[tuple]): 각 행에 해당하는 파라미터 튜플의 리스트.
                         예) [('PAYMENT', '...'), ('IP_OWNERSHIP', '...'), ...]
            chunk_size (int): 한 번에 처리할 행 수. 기본값 1000.
                              데이터가 매우 많을 경우 메모리 초과를 방지합니다.

        Returns:
            int: 성공적으로 삽입된 총 행 수. 실패 시 -1 반환.

        Example:
           rows = [('PAYMENT', '...'), ('IP_OWNERSHIP', '...')]
           query = "INSERT INTO standard_clauses (category, text) VALUES (?, ?)"
           inserted = db.execute_many(query, rows)
           logging.error(f"{inserted}건 삽입 완료")
        """
        conn = self.connect()
        if not conn:
            return -1

        cursor = conn.cursor()
        total_affected = 0
        try:
            # chunk_size 단위로 나누어 처리 (대용량 데이터 안정성 확보)
            for i in range(0, len(params_list), chunk_size):
                chunk = params_list[i:i + chunk_size]
                cursor.executemany(query, chunk)
                total_affected += cursor.rowcount
            conn.commit()
            return total_affected
        except sqlite3.Error as e:
            logging.error(f"배치 쿼리 실행 오류: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()

    def fetch_all(self, query: str, params: tuple | list | dict | str | int | None = None):
        """
        여러 줄의 데이터를 조회(SELECT)할 때 사용합니다.
        결과를 딕셔너리 리스트([{'col1': val1, ...}, ...]) 형태로 반환합니다.
        """
        if isinstance(params, (str, int, float, bool)):
            params = (params,)
        conn = self.connect()
        if not conn:
            return []
            
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            return [dict(row) for row in result]
        except sqlite3.Error as e:
            logging.error(f"데이터 조회 오류: {e}")
            raise
        finally:
            cursor.close()

    def fetch_one(self, query: str, params: tuple | list | dict | str | int | None = None):
        """단일 행의 데이터를 조회할 때 사용합니다. 딕셔너리 하나를 반환합니다."""
        if isinstance(params, (str, int, float, bool)):
            params = (params,)
        conn = self.connect()
        if not conn:
            return None
            
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            return dict(result) if result else None
        except sqlite3.Error as e:
            logging.error(f"데이터 단일 조회 오류: {e}")
            raise
        finally:
            cursor.close()

    # 'with' 문 사용을 위한 컨텍스트 매니저 지원
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

# =================================================================
# 팀원 공용 DB 객체 (Single Instance)
# 사용법: from adapter import db
# 1. users = db.fetch_all("SELECT * FROM users")
# 2. db.execute_query("UPDATE users SET name=? WHERE id=?", ('Kim', 1))
# =================================================================
db = DBManager()