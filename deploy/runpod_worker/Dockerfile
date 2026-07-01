# =================================================================
# WorkShield 임베딩/리랭커 RunPod 서버리스 워커 (자체 구현)
# - src/adapter/embedding_model.py(sentence-transformers 기반) 를 그대로 재사용
# - 빌드 컨텍스트는 리포지토리 루트: docker build -f deploy/runpod_worker/Dockerfile .
# =================================================================
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

WORKDIR /app

RUN pip install --no-cache-dir runpod "sentence-transformers>=5.6.0"

# 어댑터 원본 파일을 그대로 재사용(중복 작성 금지) — adapter 패키지 __init__을 거치지 않도록
# 평평하게(flat) 복사해, kordoc·korean_law_mcp·db 등 이 워커에 불필요한 의존성을 배제한다.
COPY src/config.py ./config.py
COPY src/adapter/embedding_model.py ./embedding_model.py
COPY deploy/runpod_worker/handler.py ./handler.py

# 모델 가중치를 빌드 타임에 이미지 안에 구워 넣는다(공식 가이드 방식,
# https://docs.runpod.io/pods/templates/create-custom-template).
# 네트워크 볼륨·/runpod-volume 유무에 의존하지 않아, 콜드스타트마다 재다운로드가 없다.
ENV HF_HOME=/app/models
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('dragonkue/BGE-m3-ko'); \
CrossEncoder('dragonkue/bge-reranker-v2-m3-ko')"

CMD ["python", "-u", "handler.py"]
