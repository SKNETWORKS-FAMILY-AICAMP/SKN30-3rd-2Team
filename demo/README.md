# demo

WorkShield Streamlit 데모. MCP 서버(루트)와는 별개 프로세스/컨테이너로 실행한다.

## 실행

- 번들(docker compose, 서버+데모 한 번에): `just demo-bundle-up` → http://localhost:8501 종료는 `just demo-bundle-down`
- 로컬(비-docker, 2터미널): 터미널1 `just run-mcp streamable-http 8000`, 터미널2 `uv run --project demo streamlit run demo/streamlit_app.py`
